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

## Mevcut TX telemetrisi

Firmware başlangıçta şu başlığı gönderebilir:

```text
MOTOR FAZ SIMULASYONU | 1=HIGH -1=LOW 0=FLOAT
```

Her telemetri satırı aşağıdaki biçimdedir:

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

Altı adımlı beklenen dizi:

```text
STEP 1 | A: 1 | B: -1 | C: 0
STEP 2 | A: 1 | B: 0 | C: -1
STEP 3 | A: 0 | B: 1 | C: -1
STEP 4 | A: -1 | B: 1 | C: 0
STEP 5 | A: -1 | B: 0 | C: 1
STEP 6 | A: 0 | B: -1 | C: 1
```

Ayrıştırıcı anahtar kelimelerde büyük/küçük harfe ve ayraç çevresindeki ek
boşluklara toleranslıdır. Alan sırası, step aralığı ve faz değerleri sıkı biçimde
doğrulanır. Eşleşmeyen satır terminalde `[RX?]` olarak gösterilir ve canlı durumu
değiştirmez.

## Gelecekteki RX komutları

Her komut ASCII olarak ve `\r\n` ile sonlandırılarak gönderilir:

```text
START\r\n
STOP\r\n
STEP\r\n
RESET\r\n
PERIOD 200\r\n
STATUS\r\n
```

| Komut | Amaç |
|---|---|
| `START` | Otomatik komütasyonu başlatır. |
| `STOP` | Otomatik komütasyonu durdurur. |
| `STEP` | Bir sonraki komütasyon adımına ilerler. |
| `RESET` | Firmware durumunu başlangıç değerine getirir. |
| `PERIOD <ms>` | Step periyodunu ayarlar; UI `50`–`1000` ms kabul eder. |
| `STATUS` | Çalışma durumu, periyot ve step bilgisini ister. |

Uygulama komutları yalnızca seri bağlantı açıkken kuyruğa alır. Komut kuyruğu
worker thread tarafından yazılır; bir UI düğmesi seri yazmayı beklemez.

## Gelecekteki firmware cevapları

Başarılı komut örnekleri:

```text
OK START
OK STOP
OK PERIOD 200
```

Durum cevabı:

```text
STATUS RUN=1 PERIOD=200 STEP=3
```

Alanlar:

- `RUN`: yalnızca `0` veya `1`
- `PERIOD`: pozitif ondalık milisaniye değeri
- `STEP`: yalnızca `1`–`6`

Hata cevabı:

```text
ERR UNKNOWN_COMMAND
```

`OK`, `ERR` veya geçerli `STATUS` cevabı alındığında uygulama firmware'i komut
destekli olarak işaretler. `ERR` cevabı terminalde korunur ve durum çubuğunda
kullanıcıya bildirilir.

## Telemetry-only uyumluluğu

Mevcut firmware komutları okumadığında masaüstü uygulaması yine de komutları
bağlı port üzerinden gönderebilir; cevap gelmemesi bağlantı hatası sayılmaz.
Arayüz bu nedenle açıkça şu uyarıyı gösterir:

> Firmware telemetry-only mode: commands may be ignored.
