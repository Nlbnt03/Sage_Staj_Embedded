/**
 * hil_app.h  --  STM32 tarafi HIL uygulama katmani (NUCLEO-G491)
 *
 * Iki UART uzerinden iki ayri PC uygulamasiyla konusur:
 *
 *   USART1 (PC4/PC5, ESP_UART)  ->  HIL link (binary)   -> hil_server.py
 *        PC'deki gercek motor modeli (bldc_model.py) ile binary cercevelerle
 *        konusur. Akim PI'si buradan alinan gercek faz akimlariyla calisir.
 *
 *   LPUART1 (PA2/PA3, VCP)      ->  Telemetri (text)    -> bldc_desktop UI
 *        HIL'dan gelen gercek sensor verisini UI'nin bekledigi "DATA t=..."
 *        satirina cevirir. Mevcut bldc_desktop arayuzu hic degismeden calisir.
 *
 * URETIM / ENTEGRASYON:
 *   Bu dosyayi STM32CubeIDE projesinin Core/Inc klasorune kopyalayin,
 *   hil_app.c'yi de Core/Src klasorune kopyalayin. Geri kalan entegrasyon
 *   adimlari icin bldc_simulation/stm32/KURULUM_NUCLEO_G491.md dosyasina
 *   bakin.
 */
#ifndef HIL_APP_H
#define HIL_APP_H

#include <stdint.h>
#include <stdbool.h>

#include "hil_link.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ---- PI ayar parametreleri (six-step, Vdc=24 V, Ls=300 uH, Rs=0.35 ohm) --- */
/*  Kp = 2*pi*fbw*(2*Ls)/Vdc ,  Ki = 2*pi*fbw*(2*Rs)/Vdc  (fbw=800 Hz)       */
#define HIL_APP_KP          0.1257f
#define HIL_APP_KI          146.6f
#define HIL_APP_TS          1e-4f     /* kontrol periyodu [s] = 100 us */
#define HIL_APP_DUTY_MAX    0.95f
#define HIL_APP_IREF        4.0f      /* akim referansi [A] */

/* ---------------- bildirimler (main.c'de tanimlayacaksiniz) --------------- */
/* USART1 (HIL link) uzerinden bloklamayan yazma */
extern void HilLink_Uart_Write(const uint8_t *d, uint16_t n);
/* LPUART1 (telemetri) uzerinden bloklamayan yazma */
extern void HilTel_Uart_Write(const uint8_t *d, uint16_t n);

/* ---------------- API ---------------------------------------------------- */
void HilApp_Init(void);
/* ilk CMD cercevesini yollayarak modele el sikisir (main.c baslangicinda) */
void HilApp_Start(void);
/* USART1 RX bayti geldiginde cagirin (kesme veya DMA yarim/tam buffer) */
void HilApp_OnHilRxByte(uint8_t b);
/* telemetri satirini LPUART1 uzerinden basar (main.c ana dongusune) */
void HilApp_SendTelemetry(void);

/* ayar fonksiyonlari */
void HilApp_SetCurrentRef(float amps);   /* akim referansi [A] */
void HilApp_SetDirection(int dir);       /* +1 FWD, -1 REV      */
void HilApp_SetEnable(bool en);          /* kontrol ac/kapat     */

/* tanilamalar */
uint32_t HilApp_CrcErrors(void);
uint32_t HilApp_FramesOk(void);
uint32_t HilApp_CommandsSent(void);
float    HilApp_LastMeasuredCurrent(void);
float    HilApp_LastDuty(void);

#ifdef __cplusplus
}
#endif
#endif /* HIL_APP_H */
