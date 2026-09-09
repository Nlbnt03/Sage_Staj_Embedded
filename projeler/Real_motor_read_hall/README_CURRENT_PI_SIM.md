# Gerçek Hall/RPM ile sanal akım PI testi

Bu sürüm motorun mekanik hareketini, RPM'i veya encoder darbelerini simüle
etmez. Hall pinleri ve TIM2 encoder fiziksel olarak okunur. Motor sürücüsü bağlı
olmadan yalnızca PI çıkışı (`duty`) ve elektrik modelindeki faz akımı yazılımda
hesaplanır. PWM, gate, komütasyon veya driver-enable çıkışı üretilmez.

Akış:

```text
Hall oku -> sektör/faz çiftini bul
TIM2 encoder -> gerçek RPM
sanal akım -> PI geri besleme -> sanal duty
sanal duty + gerçek RPM -> elektrik modeli -> bir sonraki sanal akım
Hall + sektör + RPM + sanal akım + duty -> UART -> masaüstü UI
```

## Bağlantı ve çalışma

- Hall: `HALL0=PC0`, `HALL1=PC1`, `HALL2=PB0` (pull-up giriş).
- Encoder: `A=PA0/TIM2_CH1`, `B=PA1/TIM2_CH2`, 4096 PPR ve x4 sayım.
- UART: `LPUART1 TX=PA2`, `RX=PA3`, 4 Mbaud, 8N1.
- Kontrol/model adımı 10 ms, UART telemetrisi 1 ms (1 kHz)'dir.
- UART TX, DMA1 Channel 1 ile bloklamadan gönderilir. Önceki çerçeve bitmediyse
  kontrol döngüsü bekletilmez; çerçeve atlanır ve `g_uart_dropped_frames` artar.

STM32CubeIDE Live Expressions'a `g_control_inputs` ve `g_control_state`
eklenebilir. Ayarlar `g_control_inputs` üzerinden değiştirilir:

| Alan | Varsayılan | Anlamı |
|---|---:|---|
| `target_current_a` | 3.0 A | PI akım referansı |
| `kp_percent_per_a` | 2.0 | Oransal kazanç, %/A |
| `ki_percent_per_a_s` | 20.0 | İntegral kazancı, %/(A·s) |
| `bus_voltage_v` | 24 V | Sanal DC bara |
| `phase_resistance_ohm` | 0.60 Ω | Sanal faz direnci |
| `phase_inductance_h` | 0.030 H | Sanal faz endüktansı |
| `bemf_constant_v_per_rad_s` | 0.050 | Sanal geri-EMK sabiti |
| `enabled` | 1 | 0 iken PI duty ve integral sıfırlanır |

Model denklemi `L·di/dt = Vbus·duty - Ke·|ωgerçek| - R·i` biçimindedir.
10 ms örneklemede kararlı kalması için geri Euler ayrıklaştırması kullanılır.
Sanal akım 0–20 A, sanal duty %0–100 aralığıyla sınırlıdır. Bu parametreler
gerçek motor ölçümü değildir; UI/STM haberleşmesi ve PI davranışı testi içindir.

## Hall sektör tablosu

| Hall H2H1H0 | Sektör | Sanal faz çifti |
|---|---:|---|
| 001 | 1 | A+ / B- |
| 101 | 2 | A+ / C- |
| 100 | 3 | B+ / C- |
| 110 | 4 | B+ / A- |
| 010 | 5 | C+ / A- |
| 011 | 6 | C+ / B- |
| 000 veya 111 | 0 | Geçersiz; duty=0 |

Motorun Hall/faz sırası farklıysa yalnızca
`CurrentPi_DecodeHall()` içindeki tablo değiştirilmelidir.

## UART telemetrisi

Her satır `DATA ` ile başlar ve `\r\n` ile biter:

```text
DATA t=100 seq=99 hall=1 sector=1 high=A low=B float=C valid=1 enc=40960 rpm=1500 iref_ma=3000 fake_i_ma=2980 err_ma=20 duty_x10=402 integral_x10=342 bemf_mv=7853 applied_mv=9648 enabled=1 drop=0
```

`iref_ma`, `fake_i_ma`, `err_ma`, `bemf_mv`, `applied_mv` tam sayı ölçekli;
`duty_x10` ve `integral_x10` değerleri 10'a bölünerek yüzdeye çevrilir.
Masaüstü UI satır sonuna kadar tamponlayıp boşlukla ayrılmış `anahtar=değer`
alanlarını ayrıştırabilir. `seq` başarıyla başlatılan DMA çerçevesinin sıra
numarası, `drop` ise UART meşgul olduğu için atlanan toplam çerçeve sayısıdır.

4 Mbaud değerinin kullanılan USB-UART/VCP dönüştürücüsü tarafından da
desteklenmesi gerekir. Desteklenmiyorsa ASCII paket kısaltılmalı veya sabit
boyutlu binary pakete geçilip daha düşük baud seçilmelidir.

## Kart olmadan model testi

```sh
cc -std=c11 -Wall -Wextra -Werror -ICore/Inc \
  Core/Src/current_pi_sim.c tests/test_current_pi_sim.c -lm \
  -o /tmp/current_pi_sim_test
/tmp/current_pi_sim_test
```
