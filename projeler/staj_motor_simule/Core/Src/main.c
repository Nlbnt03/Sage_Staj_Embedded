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
#include "usb_device.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

#include "usbd_cdc_if.h"

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* Faz halleri iki bite sigar; tablo RAM/Flash'te enum (int) tutmaz. */
typedef uint8_t PhaseState_t;
enum
{
  PHASE_FLOAT = 0U,
  PHASE_LOW   = 1U,
  PHASE_HIGH  = 2U
};

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

#define MOTOR_STEP_COUNT      6U
#define MOTOR_STEP_PERIOD_MS 10U
#define PACK_PHASES(a, b, c) ((uint8_t)((a) | ((b) << 2U) | ((c) << 4U)))
#define UNPACK_PHASE(step, n) ((PhaseState_t)(((step) >> ((n) * 2U)) & 0x03U))

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
/* USER CODE BEGIN PV */

/* Su an hangi komutasyon adimindayiz. */
static uint8_t current_step;

/* Her adimda A/B/C fazlari ikiser bit ile tek byte'a paketlenir. */
static const uint8_t commutation_table[MOTOR_STEP_COUNT] =
{
  PACK_PHASES(PHASE_HIGH,  PHASE_LOW,   PHASE_FLOAT), /* STEP 1 */
  PACK_PHASES(PHASE_HIGH,  PHASE_FLOAT, PHASE_LOW),   /* STEP 2 */
  PACK_PHASES(PHASE_FLOAT, PHASE_HIGH,  PHASE_LOW),   /* STEP 3 */
  PACK_PHASES(PHASE_LOW,   PHASE_HIGH,  PHASE_FLOAT), /* STEP 4 */
  PACK_PHASES(PHASE_LOW,   PHASE_FLOAT, PHASE_HIGH),  /* STEP 5 */
  PACK_PHASES(PHASE_FLOAT, PHASE_LOW,   PHASE_HIGH)   /* STEP 6 */
};

/* CoolTerm, etiketli "A=-1" alaninda eksi isaretini atabildigi icin saf CSV
 * kullanilir: STEP,A,B,C. snprintf kullanmamak firmware'i de kucultur. */
static const char chart_lines[MOTOR_STEP_COUNT][sizeof("1,1,-1,0\r\n")] =
{
  "1,1,-1,0\r\n",
  "2,1,0,-1\r\n",
  "3,0,1,-1\r\n",
  "4,-1,1,0\r\n",
  "5,-1,0,1\r\n",
  "6,0,-1,1\r\n"
};

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
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
  MX_USB_DEVICE_Init();
  /* USER CODE BEGIN 2 */

  uint32_t last_step_ms = HAL_GetTick();

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* SysTick zaten HAL ve USB icin calisiyor. Ayrica TIM3/HAL_TIM kodu
     * tasimadan her 10 ms'de bir komutasyon adimi uret. */
    const uint32_t now_ms = HAL_GetTick();
    if ((uint32_t)(now_ms - last_step_ms) >= MOTOR_STEP_PERIOD_MS)
    {
      last_step_ms += MOTOR_STEP_PERIOD_MS;
      Motor_Advance();
    }
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
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE2);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL.PLLM = 16;
  RCC_OscInitStruct.PLL.PLLN = 336;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV4;
  RCC_OscInitStruct.PLL.PLLQ = 7;
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
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
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
  __HAL_RCC_GPIOA_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOA, PHASE_A_Pin|PHASE_B_Pin|PHASE_C_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pins : PHASE_A_Pin PHASE_B_Pin PHASE_C_Pin */
  GPIO_InitStruct.Pin = PHASE_A_Pin|PHASE_B_Pin|PHASE_C_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */

/*
 * Bir half-bridge cikisinin YUKSEK / DUSUK / FLOAT halini,
 * ayni GPIO pinini calisma anida yeniden yapilandirarak taklit eder
 * (Bolum 6.1 / Sekil 6): OUTPUT+SET, OUTPUT+RESET veya INPUT (Hi-Z).
 */
static void Set_Phase(GPIO_TypeDef *port, uint16_t pin, PhaseState_t state)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  GPIO_InitStruct.Pin = pin;

  switch (state)
  {
    case PHASE_HIGH:
      GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
      GPIO_InitStruct.Pull = GPIO_NOPULL;
      GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
      HAL_GPIO_Init(port, &GPIO_InitStruct);
      HAL_GPIO_WritePin(port, pin, GPIO_PIN_SET);
      break;

    case PHASE_LOW:
      GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
      GPIO_InitStruct.Pull = GPIO_NOPULL;
      GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
      HAL_GPIO_Init(port, &GPIO_InitStruct);
      HAL_GPIO_WritePin(port, pin, GPIO_PIN_RESET);
      break;

    case PHASE_FLOAT:
    default:
      GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
      GPIO_InitStruct.Pull = GPIO_NOPULL;
      HAL_GPIO_Init(port, &GPIO_InitStruct);
      break;
  }
}

/*
 * Su anki adima gore 3 fazi (A,B,C) gunceller, durumu USB-CDC
 * uzerinden PC'ye yazdirir, ardindan bir sonraki adima gecer.
 */
static void Motor_Advance(void)
{
  const uint8_t packed_step = commutation_table[current_step];

  Set_Phase(PHASE_A_GPIO_Port, PHASE_A_Pin, UNPACK_PHASE(packed_step, 0U));
  Set_Phase(PHASE_B_GPIO_Port, PHASE_B_Pin, UNPACK_PHASE(packed_step, 1U));
  Set_Phase(PHASE_C_GPIO_Port, PHASE_C_Pin, UNPACK_PHASE(packed_step, 2U));

  /* CDC_Transmit_FS bloklamaz: USB tamponu doluysa USBD_BUSY doner;
   * ana dongu bekletilmeden yalnizca o CSV satiri atlanir. */
  CDC_Transmit_FS((uint8_t *)chart_lines[current_step],
                  (uint16_t)(sizeof(chart_lines[0]) - 1U));

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
