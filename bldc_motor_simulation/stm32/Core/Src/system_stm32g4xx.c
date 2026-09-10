/**
  ******************************************************************************
  * @file    system_stm32g4xx.c
  * @brief   CMSIS Cortex-M4 Device Peripheral Access Layer System Source File.
  ******************************************************************************
  */
#include "stm32g4xx.h"

#if !defined (HSE_VALUE)
  #define HSE_VALUE    8000000U
#endif

#if !defined (HSI_VALUE)
  #define HSI_VALUE    16000000U
#endif

uint32_t SystemCoreClock = 170000000U;
const uint8_t AHBPrescTable[16] = {0,0,0,0,0,0,0,0,1,2,3,4,6,7,8,9};
const uint8_t APBPrescTable[8]  = {0,0,0,0,1,2,3,4};

void SystemInit(void)
{
  __IO uint32_t tmpreg;

  /* FPU settings */
#if (__FPU_PRESENT == 1) && (__FPU_USED == 1)
  SCB->CPACR |= ((3UL << (10*2)) | (3UL << (11*2)));
#endif

  /* RCC clock enable -- tmpreg dummy read for volatile compliance */
  tmpreg = RCC->CR;
  (void)tmpreg;

  /* Reset CFGR */
  RCC->CFGR  = 0x00000000U;
  /* Reset CR */
  RCC->CR   &= 0xEAF6ED7FU;
  /* Reset PLLCFGR */
  RCC->PLLCFGR = 0x24003010U;
  /* Reset HSEON, CSSON, PLLON */
  RCC->CR   &= 0xEAF6EDFFU;
  /* Reset HSEBYP */
  RCC->CR   &= 0xFFFFFBFFU;
  /* Reset PLLSRC, PLLM, PLLN, PLLP, PLLQ, PLLR */
  RCC->PLLCFGR &= 0x02FCFF00U;
  /* Reset PLLPEN, PLLPSEL */
  RCC->PLLCFGR &= 0xFFC7FFFFU;
  /* Reset HSEPRE */
  RCC->CFGR2 = 0x00000000U;
  /* Reset MCOSEL */
  RCC->CFGR  &= 0x8FFFFFFFU;
  /* Reset MCOPRE */
  RCC->CFGR2 &= 0xFFFFFFF0U;
  /* Reset I2SSRC */
  RCC->CFGR  &= 0xEFFFFFFFU;
  /* Clear all interrupts */
  RCC->CICR   = 0x7F000000U;
}

void SystemCoreClockUpdate(void)
{
  uint32_t pllm, plln, pllr, pllsrc, hpre, ppre1, sws;

  /* Get SYSCLK source */
  sws = RCC->CFGR & RCC_CFGR_SWS;

  switch (sws)
  {
    case 0x00: /* HSI */
      SystemCoreClock = (uint32_t)(HSI_VALUE >> ((RCC->CR & RCC_CR_HSIDIV) >> 3));
      break;

    case 0x08: /* MSI */
      SystemCoreClock = (uint32_t)(4000U << ((RCC->CR & RCC_CR_MSIRANGE) >> 4));
      break;

    case 0x10: /* HSE */
      SystemCoreClock = HSE_VALUE;
      break;

    case 0x18: /* PLL */
      pllsrc = (RCC->PLLCFGR & RCC_PLLCFGR_PLLSRC);
      pllm   = (RCC->PLLCFGR & RCC_PLLCFGR_PLLM) >> RCC_PLLCFGR_PLLM_Pos;
      plln   = (RCC->PLLCFGR & RCC_PLLCFGR_PLLN) >> RCC_PLLCFGR_PLLN_Pos;
      pllr   = (((RCC->PLLCFGR & RCC_PLLCFGR_PLLR) >> RCC_PLLCFGR_PLLR_Pos) + 1U) * 2U;

      if (pllsrc == 0x01)
        SystemCoreClock = (uint32_t)(((HSI_VALUE / (pllm + 1U)) * plln) / pllr);
      else if (pllsrc == 0x02)
        SystemCoreClock = (uint32_t)(((HSE_VALUE / (pllm + 1U)) * plln) / pllr);
      else
        SystemCoreClock = 0U;
      break;

    default:
      SystemCoreClock = HSI_VALUE;
      break;
  }

  /* HCLK */
  hpre = (RCC->CFGR & RCC_CFGR_HPRE) >> RCC_CFGR_HPRE_Pos;
  SystemCoreClock >>= AHBPrescTable[hpre];

  /* PCLK1 */
  ppre1 = (RCC->CFGR & RCC_CFGR_PPRE1) >> RCC_CFGR_PPRE1_Pos;
  (void)ppre1;
}
