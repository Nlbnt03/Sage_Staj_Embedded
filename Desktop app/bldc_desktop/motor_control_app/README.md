# STM32 BLDC Commutation Monitor

PyQt6 ile geliştirilmiş bu macOS masaüstü uygulaması, STM32 NUCLEO-G491RE
kartının altı adımlı BLDC komütasyon telemetrisini UART üzerinden izler. Faz
durumlarını kartlar ve gerçek zamanlı grafik üzerinde, Hall komütasyon adımlarını
ise ayrı bir gerçek zamanlı grafik üzerinde gösterir; gelecekteki RX
komut protokolünü göndermeye hazırdır.

Uygulama açılışta seri porta otomatik bağlanmaz. `/dev/cu.usbmodem...` portları
listede yıldızla işaretlenir ve diğer portlardan önce gösterilir.

## Gereksinimler

- macOS
- Python 3.11 veya daha yeni
- STM32 kartına bağlı uygun bir USB data kablosu
- Firmware UART ayarı: **115200 baud, 8 data bit, parity none, 1 stop bit,
  flow control none**

## Kurulum

Terminal'de proje dizinine girin:

```bash
cd motor_control_app
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Sistemde `python3.11` adı yoksa, Python 3.11+ sürümünü gösteren `python3`
komutunu kullanabilirsiniz.

## Çalıştırma

Sanal ortam etkin ve `motor_control_app` dizini geçerli dizinken:

```bash
python main.py
```

Ardından:

1. **Refresh Ports** ile portları yeniden tarayın.
2. NUCLEO kartına ait `/dev/cu.usbmodem...` portunu seçin.
3. Baud rate değerini firmware ile eşleştirin; varsayılan `115200`'dür.
4. **Connect** düğmesine basın.
5. Geçerli `HALL,raw=...` satırları geldiğinde faz kartları ile faz ve Hall
   grafikleri güncellenir.
6. Oturumu kapatmak için **Disconnect** düğmesini kullanın.

## Arayüz davranışı

- Seri port açma, okuma ve yazma işlemleri ayrı bir `QThread` içinde yürür;
  arayüz thread'i seri okuma beklemez.
- Bağlantı yeşil, bağlantı kurulma/kapanma süreci sarı, bağlantısız durum kırmızı
  gösterilir.
- UART terminali sol alt bölümde; faz, Hall ve encoder grafikleri sağ tarafta
  alt alta, yeniden boyutlandırılabilir bir alanda gösterilir.
- Hall grafiği STM telemetrisindeki `step` değerini 0–6 arasında izler. Geçerli
  ileri akış yükselen, geri akış düşen basamaklar halinde görünür; `0`
  geçersiz Hall kodudur. Firmware `step` alanı sabit kaldığı halde fazlar
  değişiyorsa etkin adım `a/b/c` kombinasyonundan türetilir; terminalde
  `phase_step` olarak belirtilir.
- Encoder grafiği arayüzde hazırdır. Mevcut STM protokolü encoder alanı
  içermediğinden veri gelene kadar bekleme durumunda kalır.
- Üç grafiğin zaman ölçekleri birlikte değişir.
- Her grafik bellekte son 60 saniyeyi tutar ve **Time scale** seçimiyle son
  1, 2, 5, 10, 30 veya 60 saniyeyi gösterebilir. Kısa ölçekler sık komütasyon
  geçişlerini yatayda açar. Süresi dolan örnekler silinir ve tampon en fazla
  6000 örnek tutar.
- Zaman ekseni sistem saatine değil son telemetri örneğine bağlıdır. Telemetri
  durduğunda grafik kaymaz; yeni örnek geldiğinde kaldığı yerden ilerler.
- Geçersiz veya tanınmayan UART satırları `[RX?]` etiketiyle terminalde kalır;
  aktif step, faz kartları veya grafik bu satırlardan etkilenmez.
- Terminal en fazla 5000 satır tutar. **Save Log** görünen oturumu UTF-8 bir
  `.log` dosyasına kaydeder.
- Seri kablo çıkarılırsa worker hatayı yakalar, portu kapatır, kontrolleri
  bağlantısız duruma getirir ve kullanıcıya anlaşılır bir hata penceresi gösterir.

## Otomatik telemetri modu

Arayüz STM32'ye çalışma komutu göndermez. **Connect** yalnızca seri portu açar;
faz üretimi STM32 açıldığı anda otomatik başlar. ESP'den gelen Hall değişimleri
STM32 tarafından `HALL,...` satırlarına dönüştürülür ve grafikler bu satırlardaki
`step` ile `a/b/c` alanlarından güncellenir.

## Sorun giderme

Port listede görünmüyorsa:

- USB kablosunun yalnızca şarj kablosu olmadığını doğrulayın.
- Kartı çıkarıp tekrar taktıktan sonra **Refresh Ports** düğmesine basın.
- Aynı portu kullanan başka bir seri terminali kapatın.
- macOS System Information > USB altında STMicroelectronics/NUCLEO aygıtını
  kontrol edin.

Telemetri terminalde görünüyor ama göstergeler güncellenmiyorsa firmware
satırlarının [protocol.md](protocol.md) içindeki boşluklara toleranslı fakat alan
sırası ve değerleri sıkı olan formatla eşleştiğini kontrol edin. Faz değerleri
yalnızca `-1`, `0` veya `1`; step yalnızca `1`–`6` olabilir.

## Dizin yapısı

```text
motor_control_app/
├── main.py
├── models/
│   └── telemetry.py
├── services/
│   ├── serial_ports.py
│   └── serial_worker.py
├── ui/
│   ├── main_window.py
│   ├── theme.py
│   └── widgets.py
├── requirements.txt
├── README.md
└── protocol.md
```
