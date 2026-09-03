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

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */
typedef uint8_t PhaseState_t;

enum
{
  PHASE_FLOAT = 0U,
  PHASE_LOW   = 1U,
  PHASE_HIGH  = 2U
};

/* Her faz iki bit ile tutulur: 0=FLOAT, 1=LOW, 2=HIGH. */
typedef union
{
  struct
  {
    uint8_t phase_a  : 2;
    uint8_t phase_b  : 2;
    uint8_t phase_c  : 2;
    uint8_t reserved : 2;
  } bits;
  uint8_t val;
} U_PHASE;
/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define MOTOR_STEP_COUNT      6U
#define MOTOR_STEP_PERIOD_MS 200U

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
UART_HandleTypeDef hlpuart1;

/* USER CODE BEGIN PV */

/* Geçerli komutasyon adımı: 0 = STEP 1, 5 = STEP 6. */
static uint8_t current_step;

/* O anda GPIO'lara uygulanan A/B/C faz durumu. */
static U_PHASE phases;

/* Her komutasyon adımı doğrudan U_PHASE bit alanlarıyla tanımlanır. */
static const U_PHASE commutation_table[MOTOR_STEP_COUNT] =
{
  { .bits = { PHASE_HIGH,  PHASE_LOW,   PHASE_FLOAT, 0U } },
  { .bits = { PHASE_HIGH,  PHASE_FLOAT, PHASE_LOW,   0U } },
  { .bits = { PHASE_FLOAT, PHASE_HIGH,  PHASE_LOW,   0U } },
  { .bits = { PHASE_LOW,   PHASE_HIGH,  PHASE_FLOAT, 0U } },
  { .bits = { PHASE_LOW,   PHASE_FLOAT, PHASE_HIGH,  0U } },
  { .bits = { PHASE_FLOAT, PHASE_LOW,   PHASE_HIGH,  0U } }
};

/* CoolTerm terminali için okunaklı telemetri satırları. */
static const char chart_lines[MOTOR_STEP_COUNT]
                             [sizeof("STEP 1 | A: 1 | B: -1 | C: 0\r\n")] =
{
  "STEP 1 | A: 1 | B: -1 | C: 0\r\n",
  "STEP 2 | A: 1 | B: 0 | C: -1\r\n",
  "STEP 3 | A: 0 | B: 1 | C: -1\r\n",
  "STEP 4 | A: -1 | B: 1 | C: 0\r\n",
  "STEP 5 | A: -1 | B: 0 | C: 1\r\n",
  "STEP 6 | A: 0 | B: -1 | C: 1\r\n"
};

static const char chart_legend[] =
  "MOTOR FAZ SIMULASYONU | 1=HIGH -1=LOW 0=FLOAT\r\n";

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_LPUART1_UART_Init(void);
/* USER CODE BEGIN PFP */

static void Set_Phase(GPIO_TypeDef *port, uint16_t pin, PhaseState_t state);
static void Motor_Advance(void);

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

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
  /* USER CODE BEGIN 2 */

  uint32_t last_step_ms = HAL_GetTick();

  (void)HAL_UART_Transmit(&hlpuart1,
                          (uint8_t *)chart_legend,
                          (uint16_t)(sizeof(chart_legend) - 1U),
                          100U);

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
    const uint32_t now_ms = HAL_GetTick();

    if ((uint32_t)(now_ms - last_step_ms) >= MOTOR_STEP_PERIOD_MS)
    {
      last_step_ms += MOTOR_STEP_PERIOD_MS;
      Motor_Advance();
    }
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
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(PHASE_A_GPIO_Port, PHASE_A_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOB, PHASE_B_Pin|PHASE_C_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin : PHASE_A_Pin */
  GPIO_InitStruct.Pin = PHASE_A_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(PHASE_A_GPIO_Port, &GPIO_InitStruct);

  /*Configure GPIO pins : PHASE_B_Pin PHASE_C_Pin */
  GPIO_InitStruct.Pin = PHASE_B_Pin|PHASE_C_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */

/* Fazı aktif HIGH, aktif LOW veya yüksek empedans (FLOAT) durumuna getirir. */
static void Set_Phase(GPIO_TypeDef *port, uint16_t pin, PhaseState_t state)
{
  GPIO_InitTypeDef gpio = {0};

  gpio.Pin = pin;
  gpio.Pull = GPIO_NOPULL;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;

  if (state == PHASE_FLOAT)
  {
    gpio.Mode = GPIO_MODE_INPUT;
    HAL_GPIO_Init(port, &gpio);
  }
  else
  {
    gpio.Mode = GPIO_MODE_OUTPUT_PP;
    HAL_GPIO_Init(port, &gpio);
    HAL_GPIO_WritePin(port, pin,
                      (state == PHASE_HIGH) ? GPIO_PIN_SET : GPIO_PIN_RESET);
  }
}

/* Bir sonraki BLDC komutasyon adımını uygular ve CoolTerm'e yollar. */
static void Motor_Advance(void)
{
  phases = commutation_table[current_step];

  Set_Phase(PHASE_A_GPIO_Port, PHASE_A_Pin,
            (PhaseState_t)phases.bits.phase_a);
  Set_Phase(PHASE_B_GPIO_Port, PHASE_B_Pin,
            (PhaseState_t)phases.bits.phase_b);
  Set_Phase(PHASE_C_GPIO_Port, PHASE_C_Pin,
            (PhaseState_t)phases.bits.phase_c);

  (void)HAL_UART_Transmit(&hlpuart1,
                          (uint8_t *)chart_lines[current_step],
                          (uint16_t)(sizeof(chart_lines[0]) - 1U),
                          10U);

  current_step++;
  if (current_step >= MOTOR_STEP_COUNT)
  {
    current_step = 0U;
  }
}

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
