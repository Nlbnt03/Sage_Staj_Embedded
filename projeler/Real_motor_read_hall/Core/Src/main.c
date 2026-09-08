/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <stdio.h>
#include "motor_sim.h"
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define ENCODER_PPR             4096U
/* TIM_ENCODERMODE_TI12 = 4x decoding: her PPR cizgisi 4 sayima karsilik gelir. */
#define ENCODER_COUNTS_PER_REV  (ENCODER_PPR * 4U)
/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
UART_HandleTypeDef hlpuart1;
TIM_HandleTypeDef htim2;

/* USER CODE BEGIN PV */
#if MOTOR_SIMULATION
/* STM32CubeIDE Live Expressions uzerinden girisler degistirilebilir. */
volatile MotorSimInputs g_sim_inputs = MOTOR_SIM_DEFAULT_INPUTS;
volatile MotorSimState g_sim_state;
volatile uint32_t g_sim_skipped_steps = 0U;
volatile uint32_t g_sim_uart_errors = 0U;
static MotorSimState motorSim;
#endif

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_LPUART1_UART_Init(void);
static void MX_TIM2_Init(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
#if MOTOR_SIMULATION
static void Print_Simulation_State(void)
{
  char msg[320];
  /* Her satir tek ornek: CRLF ile biter, alanlar boslukla ayrilir.
     nano printf %f gerektirmez: x10 / 10, x10000 / 10000 olarak okunur.
     Ayarlar, RPM ile ayni sim adiminda kullanilmis degerlerdir. */
  int len = snprintf(msg, sizeof(msg),
      "SIM t=%lu target=%ld rpm=%ld err=%ld duty_x10=%ld "
      "model_rpm=%ld enc_cnt=%lu integral_x10=%ld "
      "kp_x10000=%ld ki_x10000=%ld kd_x10000=%ld load_rpm=%ld enabled=%lu\r\n",
      (unsigned long)motorSim.elapsed_ms, (long)motorSim.target_rpm,
      (long)motorSim.measured_rpm, (long)motorSim.error_rpm,
      (long)(motorSim.duty_percent * 10.0f + 0.5f),
      (long)motorSim.model_rpm, (unsigned long)motorSim.encoder_count,
      (long)(motorSim.integral_percent * 10.0f + 0.5f),
      (long)(motorSim.applied_inputs.kp * 10000.0f + 0.5f),
      (long)(motorSim.applied_inputs.ki * 10000.0f + 0.5f),
      (long)(motorSim.applied_inputs.kd * 10000.0f + 0.5f),
      (long)motorSim.applied_inputs.load_rpm,
      (unsigned long)motorSim.applied_inputs.enabled);

  /* En uzun satir da 115200 baud / 8N1'de 30 ms'den kisa surer.
     Hata durumunda eksik/tasmis bir ornegi UI'ya gonderme. */
  if (len <= 0 || len >= (int)sizeof(msg))
  {
    ++g_sim_uart_errors;
    return;
  }
  if (HAL_UART_Transmit(&hlpuart1, (uint8_t *)msg, (uint16_t)len, 40U) != HAL_OK)
  {
    ++g_sim_uart_errors;
  }
}
#else

/**
  * @brief  3 Hall pinini okuyup tek bir 3-bit degere paketler.
  *         bit0 = HALL0 (PC0), bit1 = HALL1 (PC1), bit2 = HALL2 (PB0)
  * @retval 0-7 arasi hall durumu (BLDC icin gecerli degerler 1-6'dir)
  */
static uint8_t Read_Hall_State(void)
{
  uint8_t h0 = HAL_GPIO_ReadPin(HALL0_GPIO_Port, HALL0_Pin);
  uint8_t h1 = HAL_GPIO_ReadPin(HALL1_GPIO_Port, HALL1_Pin);
  uint8_t h2 = HAL_GPIO_ReadPin(HALL2_GPIO_Port, HALL2_Pin);

  return (uint8_t)((h2 << 2) | (h1 << 1) | h0);
}

/**
  * @brief  Hall durumunu okunabilir bir satir olarak LPUART1 uzerinden yollar.
  */
static void Print_Hall_State(uint8_t hallState)
{
  char msg[48];
  int len = snprintf(msg, sizeof(msg), "HALL: %d%d%d (state=%u)\r\n",
                      (hallState >> 2) & 1, (hallState >> 1) & 1, hallState & 1,
                      hallState);

  HAL_UART_Transmit(&hlpuart1, (uint8_t *)msg, (uint16_t)len, HAL_MAX_DELAY);
}

/**
  * @brief  TIM2'nin 32-bit encoder sayacini okur (yon dahil, isaretli).
  */
static int32_t Read_Encoder_Count(void)
{
  return (int32_t)__HAL_TIM_GET_COUNTER(&htim2);
}

/**
  * @brief  Encoder sayacini konum (derece) ve hiz (RPM) ile birlikte LPUART1
  *         uzerinden yollar. RPM, en son iki okuma arasindaki sayim farkindan
  *         hesaplanir; delta_ms=0 ise (ilk okuma) rpm=0 yazilir.
  *         --specs=nano.specs printf %f'yi desteklemedigi icin tum hesap
  *         tam sayi (64-bit ara sonuc) ile yapilir.
  */
static void Print_Encoder_State(int32_t count, int32_t delta_count, uint32_t delta_ms)
{
  int32_t degrees = (int32_t)(((int64_t)count * 360LL) / (int64_t)ENCODER_COUNTS_PER_REV);
  int32_t rpm = 0;
  char msg[64];
  int len;

  if (delta_ms > 0U)
  {
    rpm = (int32_t)(((int64_t)delta_count * 60000LL) /
                     ((int64_t)ENCODER_COUNTS_PER_REV * (int64_t)delta_ms));
  }

  len = snprintf(msg, sizeof(msg), "ENC: cnt=%ld deg=%ld rpm=%ld\r\n",
                 (long)count, (long)degrees, (long)rpm);

  HAL_UART_Transmit(&hlpuart1, (uint8_t *)msg, (uint16_t)len, HAL_MAX_DELAY);
}

#endif /* MOTOR_SIMULATION */
/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_LPUART1_UART_Init();
  MX_TIM2_Init();
  /* USER CODE BEGIN 2 */
#if MOTOR_SIMULATION
  uint32_t lastSimMs = HAL_GetTick();
  uint32_t lastSimPrintMs = lastSimMs;
  MotorSim_Init(&motorSim);
  g_sim_state = motorSim;
  /* TIM2 encoder baslatilmaz. PID cikisi sadece motor modeline verilir.
     PWM, komutasyon ve motor surucu enable cikisi yoktur. */
#else
  uint8_t lastHallState = 0xFF; /* gecersiz baslangic degeri, ilk okumada mutlaka yazdirsin */
  int32_t lastEncoderCount;
  uint32_t lastEncoderPrintMs = HAL_GetTick();

  /* Encoder sayacini baslat: TIM2->CNT donen mile gore artar/azalir. */
  HAL_TIM_Encoder_Start(&htim2, TIM_CHANNEL_ALL);
  lastEncoderCount = Read_Encoder_Count();
  Print_Encoder_State(lastEncoderCount, 0, 0U);
#endif
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
#if MOTOR_SIMULATION
    uint32_t nowMs = HAL_GetTick();
    uint32_t steps = 0U;
    /* UART gecikmesinde sabit dt ile yetis; debugger duraklamasinda
       sinirsiz sayida gecmis adim calistirma. Tick tasmasi unsigned'dir. */
    while ((uint32_t)(nowMs - lastSimMs) >= MOTOR_SIM_STEP_MS && steps < 5U)
    {
      const MotorSimInputs inputs = g_sim_inputs;
      MotorSim_Step(&motorSim, &inputs);
      lastSimMs += MOTOR_SIM_STEP_MS;
      ++steps;
    }
    if ((uint32_t)(nowMs - lastSimMs) >= MOTOR_SIM_STEP_MS)
    {
      g_sim_skipped_steps += (uint32_t)(nowMs - lastSimMs) / MOTOR_SIM_STEP_MS;
      lastSimMs = nowMs;
    }
    g_sim_state = motorSim;
    if ((uint32_t)(nowMs - lastSimPrintMs) >= 100U)
    {
      lastSimPrintMs = nowMs;
      Print_Simulation_State();
    }
#else
    uint8_t hallState = Read_Hall_State();

    if (hallState != lastHallState)
    {
      Print_Hall_State(hallState);
      lastHallState = hallState;
    }

    if ((uint32_t)(HAL_GetTick() - lastEncoderPrintMs) >= 100U)
    {
      int32_t encoderCount = Read_Encoder_Count();
      uint32_t now_ms = HAL_GetTick();
      uint32_t delta_ms = now_ms - lastEncoderPrintMs;

      lastEncoderPrintMs = now_ms;
      if (encoderCount != lastEncoderCount)
      {
        Print_Encoder_State(encoderCount, encoderCount - lastEncoderCount, delta_ms);
        lastEncoderCount = encoderCount;
      }
    }

#endif
    HAL_Delay(1);
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1_BOOST);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL.PLLM = RCC_PLLM_DIV4;
  RCC_OscInitStruct.PLL.PLLN = 85;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = RCC_PLLQ_DIV2;
  RCC_OscInitStruct.PLL.PLLR = RCC_PLLR_DIV2;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_4) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief LPUART1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_LPUART1_UART_Init(void)
{

  /* USER CODE BEGIN LPUART1_Init 0 */

  /* USER CODE END LPUART1_Init 0 */

  /* USER CODE BEGIN LPUART1_Init 1 */

  /* USER CODE END LPUART1_Init 1 */
  hlpuart1.Instance = LPUART1;
  hlpuart1.Init.BaudRate = 115200;
  hlpuart1.Init.WordLength = UART_WORDLENGTH_8B;
  hlpuart1.Init.StopBits = UART_STOPBITS_1;
  hlpuart1.Init.Parity = UART_PARITY_NONE;
  hlpuart1.Init.Mode = UART_MODE_TX_RX;
  hlpuart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  hlpuart1.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
  hlpuart1.Init.ClockPrescaler = UART_PRESCALER_DIV1;
  hlpuart1.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;
  if (HAL_UART_Init(&hlpuart1) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_UARTEx_SetTxFifoThreshold(&hlpuart1, UART_TXFIFO_THRESHOLD_1_8) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_UARTEx_SetRxFifoThreshold(&hlpuart1, UART_RXFIFO_THRESHOLD_1_8) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_UARTEx_DisableFifoMode(&hlpuart1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN LPUART1_Init 2 */

  /* USER CODE END LPUART1_Init 2 */

}

/**
  * @brief TIM2 Initialization Function (Encoder Mode)
  * @param None
  * @retval None
  */
static void MX_TIM2_Init(void)
{
  TIM_Encoder_InitTypeDef sConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  htim2.Instance = TIM2;
  htim2.Init.Prescaler = 0;
  htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim2.Init.Period = 4294967295;
  htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  sConfig.EncoderMode = TIM_ENCODERMODE_TI12;
  sConfig.IC1Polarity = TIM_ICPOLARITY_RISING;
  sConfig.IC1Selection = TIM_ICSELECTION_DIRECTTI;
  sConfig.IC1Prescaler = TIM_ICPSC_DIV1;
  sConfig.IC1Filter = 6;
  sConfig.IC2Polarity = TIM_ICPOLARITY_RISING;
  sConfig.IC2Selection = TIM_ICSELECTION_DIRECTTI;
  sConfig.IC2Prescaler = TIM_ICPSC_DIV1;
  sConfig.IC2Filter = 6;
  if (HAL_TIM_Encoder_Init(&htim2, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim2, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pins : HALL0_Pin HALL1_Pin */
  GPIO_InitStruct.Pin = HALL0_Pin|HALL1_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

  /*Configure GPIO pin : HALL2_Pin */
  GPIO_InitStruct.Pin = HALL2_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(HALL2_GPIO_Port, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
