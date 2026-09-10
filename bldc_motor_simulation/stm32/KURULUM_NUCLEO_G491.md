# NUCLEO-G491 ↔ BLDC HIL + bldc_desktop UI — Kurulum Rehberi

Bu dokuman, STM32G491 Nucleo'nun iki ayri PC uygulamasiyla ayni anda
haberlesmesini kurar:

```
  PC: hil_server.py (bldc_model)      PC: bldc_desktop (PyQt6 UI)
      (binary HIL protokol)                (ASCII text telemetri)
                  │                                   ▲
   USB-Serial ────┤ (USART1)                  LPUART1 │ (ST-LINK VCP)
                  ▼                                   │
        ┌──────────────────── STM32 NUCLEO-G491 ───────────────────┐
        │  USART1: hil_link.c  (binary A5 5A ... CRC16)           │
        │  LPUART1: "DATA t=..." text telemetri (bldc_desktop)    │
        │  Current PI kontrol dongusu (100 us)                     │
        └──────────────────────────────────────────────────────────┘
```

- **Kanal 1 (USART1, PC4/PC5):** STM32 ile modelin haberlesmesi (binary).
  PC tarafinda `hil_server.py --port /dev/cu.usbserial-XXXX` cagrilir.
- **Kanal 2 (LPUART1, PA2/PA3 — ST-LINK VCP):** STM32'den UI'ya telemetri
  (text). PC tarafinda bldc_desktop acildiginda ST-LINK VCP secilir.

> Not: `stm32/` klasorunde **STM32CubeIDE** icin hazir bir proje taslagi
> vardir: `Real_motor_read_hall.ioc`. HIL dosyalari (`hil_app.c/h`,
> `hil_link.c/h`) zaten `Core/` klasorune kopyalanmis ve `main.c` /
> `stm32g4xx_it.c` icindeki USER CODE bolumleri HIL ile entegre edilmistir.
> Asagidaki adimlar bu taslagi kullanir.

---

## 0. STM32CubeIDE icin Proje Acma

`stm32/Real_motor_read_hall.ioc` dosyasini STM32CubeIDE ile acin. CubeMX,
cerceve verisinden Core/Drivers agacini yeniden uretir ve koddaki USER CODE
bolumlerini KORUR (HIL entegrasyonu kaybolmaz).

1. STM32CubeIDE -> File -> Open Projects from File System -> `stm32/`
   klasorunu secin. Ya da `.ioc` dosyasini cift tiklayip CubeIDE'da acin.
2. Tercihen: `.ioc`'u acip (CubeMX perspektifi) asagidaki **1. Bolum**deki
   USART1 / LPUART1 / DMA ayarlarini GUI'de **dogrulayin**. Pin atamalarini
   ve saat (HSE 8 MHz -> PLL -> 170 MHz SYSCLK) yapilandirmasini kontrol edin.
3. Project -> Generate Code (zaten uretildiyse sadece Build yeterli).
4. Project -> Build All. Hata yoksa `.elf` olusur.
5. Nucleo'yu ST-LINK USB ile baglayin; Run (Debug) veya Flash ile yukleyin.

> `hil_app.c` / `hil_link.c` CubeMX tarafindan YONETILMEYEN dosyalardir;
> yeniden uretimde korunur. Yalnizca bu dosyaların `main.c` ve
> `stm32g4xx_it.c` icindeki baglanti noktalari (USER CODE bolumleri) korunmalidir.

---

## 1. CubeMX Pin / Perifer Yapilandirmasi

Mevcut `Real_motor_read_hall.ioc` baz alindi. Sadece su ayarlari **dogrulayin**
(CubeMX'te degistirirseniz kodu yeniden uretin ve 4. adimi tekrar yapin):

### USART1 (HIL link) — PC4(TX) / PC5(RX)
| Ayar | Deger |
|---|---|
| Mode | Asynchronous |
| BaudRate | 115200 (sabit, asagida gerekcelendirildi) |
| WordLength / Parity / Stop | 8 bit / None / 1 |
| NVIC | USART1 global interrupt = Enabled |
| DMA | USART1_TX (DMA1_Ch2), USART1_RX (DMA1_Ch1) |

**Neden 115200?** HIL lockstep modda STM32 her komutta 18 bayt gonderir (CMD)
ve model 18 bayt geri doner (FB), kontrol periyodu 100 us. 921600'dan daha
dusuk, daha guvenilir. Model (PC) zamani yonettigi icin (lockstep) dusuk
baud hiz zihendirme yapmaz — sadece uyku bekler. Isterseniz daha yuksek
kurabilirsiniz; sadece iki tarafta ayni olmali.

### LPUART1 (UI telemetri) — PA2(TX) / PA3(RX)
| Ayar | Deger |
|---|---|
| Mode | Asynchronous |
| BaudRate | **115200** |
| NVIC | LPUART1 global interrupt = Enabled |
| DMA | LPUART1_TX (DMA1_Ch3) |

> **ONEMLI — 2000000 degil 115200 kullanin!** STM32G4 LPUART, 170 MHz PCLK1'de
> 2000000 baud URETEMEZ: baud orani `BRR = PCLK / baud` olup `LPUART_BRR_MIN`
> (768) ile sinirlidir; 170 MHz / 2000000 = 85 < 768 → gecersiz. Bu yuzden
> telemetri bozuk/ascii disi gelir. 115200 degerinde BRR ~1476 olup gecerlidir.
> bldc_desktop arayuzunde port secildikten sonra **baud = 115200** secilmelidir.

### Diger periferler (dokunmayin)
- **TIM2** encoder (PA0/PA1) — HIL modunda model encoder'i kullanildigi icin
  gerek yok ama firmware kaldiginiz yerden calismasi icin kalabilir.
- **HALL0/1/2** (PC0/PC1/PB0) — ayni sekilde HIL'de kullanilmaz, bosa koyulur.

---

## 2. Kopyalanacak Dosyalar

`bldc_simulation/stm32/` klasorundeki dosyalari STM32 projesine kopyalayin:

| Dosya | Hedef |
|---|---|
| `hil_link.h`  | `Core/Inc/hil_link.h` |
| `hil_link.c`  | `Core/Src/hil_link.c` |
| `hil_app.h`   | `Core/Inc/hil_app.h` |
| `hil_app.c`   | `Core/Src/hil_app.c` |

STM32CubeIDE'de (varsa) Eclipse build projelerinde dosyalar otomatik derlenir;
degilse `.cproject` / Makefile'a `.c` dosyalarini ekleyin.

**Onemli:** `hil_link.c` icindeki komutasyon tablosu (`k_cw`/`k_ccw`) artik
**gercek motor** (current_pi_sim.c `DecodeHall`) konvensiyonundadir ve
`bldc_model.py` `COMMUTATION_CW` ile birebir aynidir. Iki tarafi ayni tutun.

---

## 3. main.c Entegrasyonu

`Real_motor_read_hall/Core/Src/main.c` uzerinden gidin. Yapacaginiz degisiklikler:

### 3.1 Includes (`USER CODE BEGIN Includes`)
```c
#include <stdio.h>
#include "hil_app.h"
```

### 3.2 UART yazma baglayicilari (USER CODE BEGIN 4)
Bu fonksiyonlar `hil_app.c`'nin ihtiyac duydugu soyut UART yazmalaridir.
DMA devam ederken yeniden gonderim engellenir (drop sayaci):

```c
/* USER CODE BEGIN 4 */
/* USART1 (HIL link) bloklamayan yazma */
void HilLink_Uart_Write(const uint8_t *d, uint16_t n)
{
  if (huart1.gState != HAL_UART_STATE_READY) { g_hil_drops++; return; }
  if (HAL_UART_Transmit_DMA(&huart1, (uint8_t *)d, n) != HAL_OK) g_hil_drops++;
}

/* LPUART1 (UI telemetri) bloklamayan yazma */
void HilTel_Uart_Write(const uint8_t *d, uint16_t n)
{
  if (hlpuart1.gState != HAL_UART_STATE_READY) { g_tel_drops++; return; }
  if (HAL_UART_Transmit_DMA(&hlpuart1, (uint8_t *)d, n) != HAL_OK) g_tel_drops++;
}
/* USER CODE END 4 */
```

> `g_hil_drops` / `g_tel_drops` degiskenlerini `USER CODE BEGIN PV`'de
> `volatile uint32_t g_hil_drops = 0; volatile uint32_t g_tel_drops = 0;`
> olarak tanimlayin.

### 3.3 Baslangicta HIL'i baslat (`USER CODE BEGIN 2`)
```c
HilApp_Init();
HilApp_Start();          /* modele ilk COAST CMD gonderir (el sikisma) */
HilApp_SetCurrentRef(4.0f);
```

### 3.4 Ana dongude telemetriyi bas (`USER CODE BEGIN WHILE`)
```c
while (1)
{
  /* model zamani geldikce her FB'den sonra UI'ya bir satir bas.
     Model 100 us'de bir FB gonderdigi icin ~10 kHz text akar; UI bunu
     20 ms'lik partiler halinde alip sonorncisini kullanir. Isterseniz
     HilApp_SendTelemetry()'yi belirli periyotta (orn. her 10 donem) cagirin. */
  HilApp_SendTelemetry();
  __WFI();
}
```

### 3.5 USART1 RX kesmesi / DMA callback'i (`stm32g4xx_it.c` veya HAL callback)

Tek bayt kesmeli RX icin (`stm32g4xx_it.c` `USART1_IRQHandler` icinde):
```c
void USART1_IRQHandler(void)
{
  extern void HilApp_OnHilRxByte(uint8_t b);
  if (__HAL_UART_GET_FLAG(&huart1, UART_FLAG_RXNE) != RESET) {
    HilApp_OnHilRxByte((uint8_t)(huart1.Instance->RDR & 0xFF));
    __HAL_UART_CLEAR_FLAG(&huart1, UART_FLAG_RXNE);
  }
  HAL_UART_IRQHandler(&huart1);
}
```

DMA RX kullaniyorsaniz bunun yerine `HAL_UARTEx_RxEventCallback` / yarim-tam
tampon geri cagrisi icinde baytlari `HilApp_OnHilRxByte(...)` ile besleyin.
RS512: USART1 RX DMA ile `for (uint16_t i=0;i<n;i++) HilApp_OnHilRxByte(d[i]);`
cagrilarak da yapilir (kesme baglaminda kisa).

---

## 4. PC Tarafi Calistirma

### 4.1 HIL server (model)
```bash
cd bldc_simulation
python3 hil_server.py --port /dev/cu.usbserial-XXXX --baud 115200 \
                      --mode lockstep --fan 8e-7 --load 0.01 --live
```
- `--port`: USART1'e bagli USB-Serial adaptorunun portu (PC4/PC5 -> FT/CP210x).
- `--live`: model grafigini PC'de acar (opsiyonel).
- `--mode lockstep` onerilir: model zamani yonettigi icin STM32'nin islemi
  yeterli surede yetisir.

### 4.2 UI (telemetri izleyici)
1. bldc_desktop'i acin:
   ```bash
   cd bldc_desktop/motor_control_app
   pip install -r requirements.txt
   python3 main.py
   ```
2. Port listesinden **ST-LINK VCP** (`/dev/cu.usbmodem...`) secin,
   baud = **115200**, baglanin.
3. `DATA t=...` satirlari current PI grafigini, Hall panelini, faz kartlarini
   ve commutation animasyonunu besler — modelden gelen GERCEK sensor verisi.

---

## 5. Veri Akisi Dogrulama (ilk calistirma)

1. Terminal 1: hil_server calisiyor (model, RCP bekliyor).
2. STM32 flashelaninca `HilApp_Start()` doneminde ilk COAST CMD'yi yollar →
   model cagirir → FB doner → UI'da `DATA` satirlari akar.
3. Kontrol: UI'da hall 1..6 arasi dolanir, sector/high/low degisir,
   `iref`/`fake_i_ma` (gercekte model olcum akimi) PI takibini gosterir,
   `enc` model encoder sayaci, `rpm` model hizi.

Sik karsilasilan sorunlar:

| Belirti | Cozum |
|---|---|
| UI baglaniyor ama veri yok | LPUART1 baud = 115200 mi? VCP disinda ikinci porta bagli mi? |
| hil_server hiç CMD almadi | STM32 USART1 TX=>PC5 mi bagli? TX/RX ters mi? |
| UI'da `[RX?]` gorunuyor | `DATA` satiri regex'e uymuyor — hil_app.c uretimini kontrol edin |
| Model hizli akiyor / yavas | lockstep modda normal; `--ts` ile periyot degisir |
| CRC hata artiyor | USART1 baud uyumsuz veya DMA/kesme catismasi |

---

## 6. HAL Adimlari Nasil Esitlendi?

Simulasyondaki hall komutasyon adimlari gercek motorun (firmware'deki
`current_pi_sim.c` `CurrentPi_DecodeHall`) dogrulanmis duzenine esitlendi:

| Gercek hall | Fazlar (DecodeHall) | Gate maskesi (0xAH AL BH BL CH CL) |
|---|---|---|
| 1 | A+ B- | `AH | BL` = 0x09 |
| 2 | C+ A- | `CH | AL` = 0x12 |
| 3 | C+ B- | `CH | BL` = 0x18 |
| 4 | B+ C- | `BH | CL` = 0x24 |
| 5 | A+ C- | `AH | CL` = 0x21 |
| 6 | B+ A- | `BH | AL` = 0x06 |

Bu tablo su uc yerde birbirine esittir:
- `bldc_model.py` `COMMUTATION_CW`
- `hil_link.c` `k_cw` (STM32 tarafi)
- `current_pi_sim.c` `CurrentPi_DecodeHall` (UI'nin referansi)

Model, kendi fiziksel uretiminden gelen ham hall kodunu gercek motor koduna
(`HALL_MODEL_TO_REAL`) cevirerek raporlar; bu sayede STM32 tarafinda
komutasyon tablosu degistirilmeden birebir kullanilir.