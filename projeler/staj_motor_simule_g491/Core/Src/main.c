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

typedef union
{
  struct
  {
    uint8_t hall_c : 1;
    uint8_t hall_b : 1;
    uint8_t hall_a : 1;
    uint8_t reserved : 5;
  } bits;
  uint8_t val;
} HALL_RAW;

typedef struct
{
  uint8_t raw;
  int8_t step_index;
  int8_t direction;
  uint32_t electrical_rpm;
  uint32_t mechanical_rpm;
  uint32_t last_transition_ms;
  uint8_t valid;
} HallTelemetry_t;
/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define MOTOR_STEP_COUNT            6U
#define MOTOR_STEP_PERIOD_MS      200U
/* 1: Test için Hall kodlarını yazılımsal üret. 0: PC0/PC1/PC2'den gerçek Hall oku. */
#define HALL_SIMULATION_ENABLED     0U
#define HALL_INPUT_SETTLE_MS        5U
#define HALL_STOP_TIMEOUT_MS     1000U
#define HALL_TELEMETRY_PERIOD_MS  500U
/* Gerçek mekanik RPM için motorun veri sayfasındaki kutup çifti sayısını gir. */
#define MOTOR_POLE_PAIR_COUNT       6U
#define HALL_INVALID_RAW         0xFFU
#define HALL_INVALID_STEP          (-1)

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
UART_HandleTypeDef hlpuart1;

/* USER CODE BEGIN PV */

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

/* Geçerli altı-adım dizisi için Hall kodları: ABC = 001, 101, 100, 110, 010, 011. */
#if HALL_SIMULATION_ENABLED
static const uint8_t hall_sequence[MOTOR_STEP_COUNT] =
{
  0x01U, 0x05U, 0x04U, 0x06U, 0x02U, 0x03U
};
#endif

/* İndis ham ABC Hall kodudur: 000...111; -1 geçersiz olan 000/111 içindir. */
static const int8_t hall_to_step[8] =
{
  HALL_INVALID_STEP, 0, 4, 5, 2, 1, 3, HALL_INVALID_STEP
};

static HallTelemetry_t hall_telemetry =
{
  HALL_INVALID_RAW, HALL_INVALID_STEP, 0, 0U, 0U, 0U, 0U
};

static uint8_t phase_step_index;
static uint32_t last_telemetry_ms;

#if HALL_SIMULATION_ENABLED
static uint8_t simulation_index;
#else
static uint8_t hall_candidate_raw = HALL_INVALID_RAW;
static uint32_t hall_candidate_since_ms;
#endif

static char telemetry_line[96];

static const char chart_legend[] =
  "BLDC HALL TELEMETRY | HALL=ABC | A/B/C: 1=HIGH -1=LOW 0=FLOAT\r\n";

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_LPUART1_UART_Init(void);
/* USER CODE BEGIN PFP */

static void Set_Phase(GPIO_TypeDef *port, uint16_t pin, PhaseState_t state);
#if !HALL_SIMULATION_ENABLED
static uint8_t Hall_ReadRaw(void);
#endif
static int8_t Hall_GetDirection(int8_t previous_step, int8_t next_step);
static int8_t Phase_ToTelemetryValue(PhaseState_t state);
static void Phase_ApplyStep(uint8_t step_index);
#if HALL_SIMULATION_ENABLED
static void Motor_AdvancePhase(uint32_t event_ms);
#endif
static void Hall_SendTelemetry(void);
static void Hall_Process(uint8_t raw_hall, uint32_t event_ms);
static void Hall_PollInput(uint32_t now_ms);
static void Hall_CheckStop(uint32_t now_ms);
static void Hall_SendPeriodicTelemetry(uint32_t now_ms);

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

  phase_step_index = 0U;
  Phase_ApplyStep(phase_step_index);

#if HALL_SIMULATION_ENABLED
  simulation_index = 0U;
  Hall_Process(hall_sequence[simulation_index], last_step_ms);
#else
  /* Açılışta PC0/PC1/PC2 üzerindeki mevcut ESP Hall durumunu bir kez bildir. */
  hall_candidate_raw = Hall_ReadRaw();
  hall_candidate_since_ms = last_step_ms;
  Hall_Process(hall_candidate_raw, last_step_ms);
#endif

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
    const uint32_t now_ms = HAL_GetTick();

#if HALL_SIMULATION_ENABLED
    if ((uint32_t)(now_ms - last_step_ms) >= MOTOR_STEP_PERIOD_MS)
    {
      last_step_ms += MOTOR_STEP_PERIOD_MS;
      Motor_AdvancePhase(now_ms);
    }
#endif

    Hall_PollInput(now_ms);

    Hall_CheckStop(now_ms);

    Hall_SendPeriodicTelemetry(now_ms);
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
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(PHASE_A_GPIO_Port, PHASE_A_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOB, PHASE_B_Pin|PHASE_C_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pins : HALL_A_Pin HALL_B_Pin HALL_C_Pin */
  GPIO_InitStruct.Pin = HALL_A_Pin|HALL_B_Pin|HALL_C_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_RISING_FALLING;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

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

  /* EXTI interrupt init*/
  HAL_NVIC_SetPriority(EXTI0_IRQn, 5, 0);
  HAL_NVIC_EnableIRQ(EXTI0_IRQn);
  HAL_NVIC_SetPriority(EXTI1_IRQn, 5, 0);
  HAL_NVIC_EnableIRQ(EXTI1_IRQn);
  HAL_NVIC_SetPriority(EXTI2_IRQn, 5, 0);
  HAL_NVIC_EnableIRQ(EXTI2_IRQn);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */

/* HIGH=3.3 V, LOW=0 V, FLOAT=GPIO input/yüksek empedans. */
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

/* Komütasyon tablosundaki gerçek HIGH/LOW/FLOAT durumlarını ESP hatlarına uygular. */
static void Phase_ApplyStep(uint8_t step_index)
{
  phases = commutation_table[step_index];

  Set_Phase(PHASE_A_GPIO_Port, PHASE_A_Pin,
            (PhaseState_t)phases.bits.phase_a);
  Set_Phase(PHASE_B_GPIO_Port, PHASE_B_Pin,
            (PhaseState_t)phases.bits.phase_b);
  Set_Phase(PHASE_C_GPIO_Port, PHASE_C_Pin,
            (PhaseState_t)phases.bits.phase_c);
}

#if HALL_SIMULATION_ENABLED
/* Yalnızca yazılım simülasyonunda kullanılır: komut beklemeden faz dizisini
 * bir sonraki adıma taşır ve karşılık gelen Hall kodunu üretir. Gerçek ESP
 * donanımıyla çalışırken komütasyon Hall_Process() içinden, ESP'den gelen
 * Hall koduna göre tetiklenir (bkz. aşağıdaki sensörlü komütasyon). */
static void Motor_AdvancePhase(uint32_t event_ms)
{
  phase_step_index++;
  if (phase_step_index >= MOTOR_STEP_COUNT)
  {
    phase_step_index = 0U;
  }

  Phase_ApplyStep(phase_step_index);

  simulation_index = phase_step_index;
  Hall_Process(hall_sequence[simulation_index], event_ms);
}
#endif

/* Komşu Hall adımlarının yönünü belirler: +1 ileri, -1 geri, 0 bilinmiyor/geçersiz. */
static int8_t Hall_GetDirection(int8_t previous_step, int8_t next_step)
{
  if ((previous_step < 0) || (next_step < 0))
  {
    return 0;
  }

  if ((uint8_t)next_step == (uint8_t)((previous_step + 1) % MOTOR_STEP_COUNT))
  {
    return 1;
  }

  if ((uint8_t)next_step == (uint8_t)((previous_step + MOTOR_STEP_COUNT - 1) % MOTOR_STEP_COUNT))
  {
    return -1;
  }

  return 0;
}

static int8_t Phase_ToTelemetryValue(PhaseState_t state)
{
  if (state == PHASE_HIGH)
  {
    return 1;
  }

  if (state == PHASE_LOW)
  {
    return -1;
  }

  return 0;
}

/* PyQt'nin kolayca anahtar=değer olarak ayrıştırabileceği tek UART satırı gönderir. */
static void Hall_SendTelemetry(void)
{
  const char *direction = "UNKNOWN";
  U_PHASE hall_phases = phases;
  int length;

  /*
   * UI'deki faz grafiği, ESP'den gelen Hall step'inin komütasyon karşılığını
   * gösterir. Fiziksel PA4/PB4/PB5 sürüşü bundan bağımsız olarak HIGH/LOW/FLOAT
   * üretmeye devam eder.
   */
  if ((hall_telemetry.valid != 0U) &&
      (hall_telemetry.step_index >= 0) &&
      ((uint8_t)hall_telemetry.step_index < MOTOR_STEP_COUNT))
  {
    hall_phases = commutation_table[(uint8_t)hall_telemetry.step_index];
  }

  if (hall_telemetry.direction > 0)
  {
    direction = "FWD";
  }
  else if (hall_telemetry.direction < 0)
  {
    direction = "REV";
  }

  length = snprintf(telemetry_line, sizeof(telemetry_line),
                    "HALL,raw=%u%u%u,step=%d,dir=%s,rpm=%lu,a=%d,b=%d,c=%d,valid=%u\r\n",
                    (unsigned int)((hall_telemetry.raw >> 2U) & 1U),
                    (unsigned int)((hall_telemetry.raw >> 1U) & 1U),
                    (unsigned int)(hall_telemetry.raw & 1U),
                    (int)(hall_telemetry.step_index + 1),
                    direction,
                    (unsigned long)hall_telemetry.mechanical_rpm,
                    (int)Phase_ToTelemetryValue((PhaseState_t)hall_phases.bits.phase_a),
                    (int)Phase_ToTelemetryValue((PhaseState_t)hall_phases.bits.phase_b),
                    (int)Phase_ToTelemetryValue((PhaseState_t)hall_phases.bits.phase_c),
                    (unsigned int)hall_telemetry.valid);

  if (length > 0)
  {
    uint16_t transmit_length = (length < (int)sizeof(telemetry_line)) ?
                               (uint16_t)length : (uint16_t)(sizeof(telemetry_line) - 1U);
    (void)HAL_UART_Transmit(&hlpuart1, (uint8_t *)telemetry_line, transmit_length, 20U);
    last_telemetry_ms = HAL_GetTick();
  }
}

/* Hall örneğini doğrular, STEP'e dönüştürür, hızı hesaplar ve bilgisayara bildirir. */
static void Hall_Process(uint8_t raw_hall, uint32_t event_ms)
{
  const uint8_t raw = raw_hall & 0x07U;
  const int8_t next_step = hall_to_step[raw];
  const int8_t previous_step = hall_telemetry.step_index;
  uint32_t elapsed_ms;

  if (next_step == HALL_INVALID_STEP)
  {
    hall_telemetry.raw = raw;
    hall_telemetry.step_index = HALL_INVALID_STEP;
    hall_telemetry.direction = 0;
    hall_telemetry.electrical_rpm = 0U;
    hall_telemetry.mechanical_rpm = 0U;
    hall_telemetry.valid = 0U;

    Hall_SendTelemetry();
    return;
  }

#if !HALL_SIMULATION_ENABLED
  /*
   * Sensörlü komütasyon: ESP32'nin PC0/PC1/PC2'ye sürdüğü Hall koduna karşılık
   * gelen faz adımı hemen PA4/PB4/PB5 üzerinden uygulanır. ESP32 tarafı bu üç
   * hattı okuyup kendi hallStep'i ile karşılaştırır (stableCommand==hallStep
   * ise ileri, (hallStep+3)%6 ise geri yönde tork uygular); STM32'nin bu
   * hatları ESP'den bağımsız sabit bir zamanlayıcıyla sürmesi bu kapalı
   * çevrimi kırar. Bu yüzden faz çıkışı burada, sabit periyotlu
   * Motor_AdvancePhase() yerine doğrudan Hall geri beslemesiyle güncellenir.
   */
  phase_step_index = (uint8_t)next_step;
  Phase_ApplyStep(phase_step_index);
#endif

  /* Aynı Hall durumu yeni bir ESP verisi değildir; UART'ta tekrar etme. */
  if ((hall_telemetry.valid != 0U) && (previous_step == next_step))
  {
    return;
  }

  hall_telemetry.direction = Hall_GetDirection(previous_step, next_step);
  if (hall_telemetry.valid != 0U)
  {
    elapsed_ms = event_ms - hall_telemetry.last_transition_ms;
    if (elapsed_ms > 0U)
    {
      hall_telemetry.electrical_rpm = 60000U / (MOTOR_STEP_COUNT * elapsed_ms);
      hall_telemetry.mechanical_rpm = hall_telemetry.electrical_rpm / MOTOR_POLE_PAIR_COUNT;
    }
  }

  hall_telemetry.raw = raw;
  hall_telemetry.step_index = next_step;
  hall_telemetry.last_transition_ms = event_ms;
  hall_telemetry.valid = 1U;

  Hall_SendTelemetry();
}

/*
 * Cuma günkü çalışan akıştaki gibi Hall girişlerini sürekli kontrol eder.
 * Aynı kod 5 ms kararlı kalmadan işlenmez; böylece kaçırılan EXTI kenarları da
 * yakalanır ve pinler değişirken oluşabilecek kısa ara değerler UART'a gitmez.
 */
static void Hall_PollInput(uint32_t now_ms)
{
#if !HALL_SIMULATION_ENABLED
  const uint8_t raw_hall = Hall_ReadRaw();

  if (raw_hall != hall_candidate_raw)
  {
    hall_candidate_raw = raw_hall;
    hall_candidate_since_ms = now_ms;
    return;
  }

  if ((raw_hall != hall_telemetry.raw) &&
      ((uint32_t)(now_ms - hall_candidate_since_ms) >= HALL_INPUT_SETTLE_MS))
  {
    Hall_Process(raw_hall, now_ms);
  }
#else
  (void)now_ms;
#endif
}

/* Belirlenen süre boyunca Hall geçişi yoksa UI'ye durmuş motor bilgisini yollar. */
static void Hall_CheckStop(uint32_t now_ms)
{
  if ((hall_telemetry.valid != 0U) && (hall_telemetry.mechanical_rpm != 0U) &&
      ((uint32_t)(now_ms - hall_telemetry.last_transition_ms) >= HALL_STOP_TIMEOUT_MS))
  {
    hall_telemetry.electrical_rpm = 0U;
    hall_telemetry.mechanical_rpm = 0U;
    hall_telemetry.direction = 0;
    Hall_SendTelemetry();
  }
}

#if !HALL_SIMULATION_ENABLED
static uint8_t Hall_ReadRaw(void)
{
  HALL_RAW raw = {0};

  raw.bits.hall_a = (HAL_GPIO_ReadPin(HALL_A_GPIO_Port, HALL_A_Pin) == GPIO_PIN_SET) ? 1U : 0U;
  raw.bits.hall_b = (HAL_GPIO_ReadPin(HALL_B_GPIO_Port, HALL_B_Pin) == GPIO_PIN_SET) ? 1U : 0U;
  raw.bits.hall_c = (HAL_GPIO_ReadPin(HALL_C_GPIO_Port, HALL_C_Pin) == GPIO_PIN_SET) ? 1U : 0U;

  return raw.val;
}

/* Hall okuma ana döngüde polling ile yapılır; EXTI yalnız hızlı uyanma sağlar. */
void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
  (void)GPIO_Pin;
}
#endif

/*
 * UI çalışma sırasında bağlanırsa açılış satırını kaçırabilir. Mevcut gerçek
 * PC0/PC1/PC2 durumu periyodik olarak tekrar bildirilir; Hall geçişleri ise
 * Hall_Process() tarafından beklemeden gönderilmeye devam eder.
 */
static void Hall_SendPeriodicTelemetry(uint32_t now_ms)
{
  if ((uint32_t)(now_ms - last_telemetry_ms) >= HALL_TELEMETRY_PERIOD_MS)
  {
    Hall_SendTelemetry();
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
