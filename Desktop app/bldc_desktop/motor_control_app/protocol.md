# STM32 UART Protocol

Bu belge mevcut NUCLEO-G491RE TX telemetrisini ve masaüstü uygulamasının hazır
olduğu gelecekteki RX kontrol protokolünü tanımlar.

## Taşıma katmanı

| Ayar | Değer |
|---|---|
| Baud rate | 115200 (varsayılan, UI üzerinden değiştirilebilir) |
| Data bits | 8 |
| Parity | None |
| Stop bits | 1 |
| Flow control | None |
| Metin kodlaması | UTF-8 alım, ASCII komut gönderimi |
| Satır sonu | `\r\n` (komut gönderimi) |

Port adı protokolün parçası değildir. macOS üzerinde uygulama portları dinamik
olarak tarar ve `/dev/cu.usbmodem...` ile başlayanları önceliklendirir.

## Mevcut TX telemetrisi (Hall, g491 firmware)

Firmware başlangıçta şu başlığı bir kez gönderir:

```text
BLDC HALL TELEMETRY | HALL=ABC | A/B/C: 1=HIGH -1=LOW 0=FLOAT
```

Her Hall geçişinde (veya `HALL_SIMULATION_ENABLED=1` test modunda her simüle
adımda) tek bir anahtar=değer satırı gönderilir:

```text
HALL,raw=<raw>,step=<step>,dir=<dir>,rpm=<rpm>,a=<phase_a>,b=<phase_b>,c=<phase_c>,valid=<valid>
```

Alan sınırları:

| Alan | Geçerli değerler | Açıklama |
|---|---|---|
| `raw` | 3 haneli `0`/`1` dizisi (ör. `001`) | Ham Hall kodu, sırasıyla A/B/C biti |
| `step` | `0`–`6` | 6 adımlı komütasyon adımı; `0` = geçersiz Hall kodu |
| `dir` | `FWD`, `REV`, `UNKNOWN` | Bir önceki adıma göre dönüş yönü |
| `rpm` | pozitif tam sayı | Hesaplanan mekanik RPM (`MOTOR_POLE_PAIR_COUNT`'a göre) |
| `phase_a`/`phase_b`/`phase_c` | `-1`, `0`, `1` | O anda uygulanan faz durumu |
| `valid` | `0`, `1` | `0` iken Hall kodu geçersiz (`000`/`111`); diğer tüm alanlar sıfırlanmış olur |

Örnek geçerli akış:

```text
HALL,raw=001,step=1,dir=FWD,rpm=120,a=1,b=-1,c=0,valid=1
HALL,raw=101,step=2,dir=FWD,rpm=118,a=1,b=0,c=-1,valid=1
```

Ayrıştırıcı anahtar kelimelerde büyük/küçük harfe toleranslıdır. Alan sırası ve
değer aralıkları sıkı biçimde doğrulanır. Eşleşmeyen satır terminalde `[RX?]`
olarak gösterilir ve canlı durumu değiştirmez.

Firmware'in bildirdiği `raw`, `step` ve `a/b/c` alanları aynı komütasyon adımını
göstermelidir. Birbiriyle uyuşmayan satırlar `[RX?]` olarak işaretlenir ve
grafikleri değiştirmez. Hall grafiği doğrulanmış `step` alanını doğrudan kullanır.

## Eski TX telemetrisi (yalnızca faz-only F4 firmware)

Bu format artık g491 firmware tarafından üretilmez; yalnızca eski
`staj_motor_simule` (F4) projesiyle veya benzer telemetry-only firmware ile
geriye dönük uyumluluk için ayrıştırıcıda tutulur.

Başlık:

```text
MOTOR FAZ SIMULASYONU | 1=HIGH -1=LOW 0=FLOAT
```

Telemetri satırı:

```text
STEP <step> | A: <phase_a> | B: <phase_b> | C: <phase_c>
```

Alan sınırları:

| Alan | Geçerli değerler |
|---|---|
| `step` | `1`, `2`, `3`, `4`, `5`, `6` |
| `phase_a` | `-1`, `0`, `1` |
| `phase_b` | `-1`, `0`, `1` |
| `phase_c` | `-1`, `0`, `1` |

## Veri akışı

UI bağlantısı tek yönlü telemetri alımı içindir; STM32'ye `START`, `STOP`,
`RESET`, `STEP`, `STATUS` veya periyot komutu gönderilmez. Ana donanım akışı:

```text
STM32 PA4/PB4/PB5 (faz HIGH/LOW/FLOAT) -> ESP
ESP Hall A/B/C -> STM32 PC0/PC1/PC2
STM32 LPUART1/VCP -> UI HALL telemetrisi
```
