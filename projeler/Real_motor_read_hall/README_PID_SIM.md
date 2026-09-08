# Motor RPM PID simülasyonu

Proje varsayılan olarak **sanal motorla kapalı çevrim PID** çalıştırır.
Fiziksel motor, sürücü, Hall sensörü veya enkoder bağlantısı gerekmez.
PID çıkışı yalnızca yazılımdaki motor modeline uygulanır; PWM başlatılmaz,
komütasyon yapılmaz, motor sürücü enable sinyali üretilmez.
STM32 üzerinde çalıştırılabilir; aşağıdaki bilgisayar testi kart da gerektirmez.

Akış: hedef RPM → PID → sanal duty (%0–100) → motor modeli → sanal enkoder → ölçülen RPM → PID.

## STM32CubeIDE ile kullanım

1. Projeyi Refresh edip Build Project çalıştırın. Simülasyon `Core/Inc/main.h`
   içindeki `MOTOR_SIMULATION=1` ile varsayılan olarak açıktır.
2. Karta yükleyip Debug/Resume ile çalıştırın.
3. Live Expressions/Expressions penceresine `g_sim_inputs` ve `g_sim_state`
   ekleyin. Giriş alanlarını değiştirerek deney yapın; debugger canlı yazmayı
   desteklemiyorsa Suspend → değeri değiştir → Resume kullanın.
4. UART terminalini **115200 baud, 8N1, akış kontrolü yok** olarak açın.
   Mevcut LPUART1 TX pini PA2'dir; mevcut seri port bağlantınızı kullanın.

| Değiştirilebilir alan | Başlangıç | Anlamı |
|---|---:|---|
| `g_sim_inputs.target_rpm` | 1500 | Hedef hız, 0–3000 RPM |
| `g_sim_inputs.kp` | 0.03 | Oransal kazanç, %/RPM |
| `g_sim_inputs.ki` | 0.08 | İntegral kazancı, %/(RPM·s) |
| `g_sim_inputs.kd` | 0.0005 | Türev kazancı, %·s/RPM |
| `g_sim_inputs.load_rpm` | 0 | Yükün denge hızından düşürdüğü RPM, 0–3000 |
| `g_sim_inputs.enabled` | 1 | 0: çıkışı sıfırla, serbest yavaşlama; 1: kontrolü çalıştır |

Örnek deney: hedefi 1500'den 2200'e çıkarın, ardından `load_rpm=600`
yapın. Hız önce düşer; PID duty değerini yükselterek hedefe geri getirir.
Yükü sıfırlayın ve hedefi 800'e düşürün. `target_rpm=0` veya `enabled=0`
çıkışı ve integrali sıfırlar; model aniden durmak yerine yavaşlar.
Başlangıç ayarlarını kalıcı değiştirmek için `Core/Inc/motor_sim.h` içindeki
`MOTOR_SIM_DEFAULT_INPUTS` tanımını düzenleyin.

UART her 100 ms'de şu biçimde satır üretir (değerler örnektir):

```text
SIM t=6000 target=1500 rpm=1500 err=0 duty_x10=500 model_rpm=1500 enc_cnt=2200000 integral_x10=500 kp_x10000=300 ki_x10000=800 kd_x10000=5 load_rpm=0 enabled=1
```

Her örnek `SIM ` ile başlar, boşlukla ayrılmış `alan=değer` çiftleri içerir ve
`\r\n` ile biter. Terminalde saniyede yaklaşık 10 satır görülür; UI için UART
parçalarını satır sonuna kadar biriktirip tamamlanan satırı ayrıştırın.

| UART alanı | Anlamı / dönüşüm |
|---|---|
| `t` | Simülasyon zamanı, ms |
| `target`, `rpm`, `err` | Hedef, sanal enkoderden ölçülen RPM ve hedef−ölçüm hatası |
| `duty_x10` | 10'a bölünce sanal kontrol çıkışı (%); 500 → %50.0 |
| `model_rpm` | Enkoder sayımına çevrilmeden önceki model hızı, RPM |
| `enc_cnt` | Sanal kümülatif enkoder sayacı, uint32 |
| `integral_x10` | 10'a bölünce PID integral katkısı (%) |
| `kp_x10000`, `ki_x10000`, `kd_x10000` | 10000'e bölünce kullanılan PID kazançları; 300 → 0.03, 800 → 0.08, 5 → 0.0005 |
| `load_rpm` | Kullanılan sanal yük, eşdeğer RPM kaybı |
| `enabled` | Kontrol izin bayrağı, 0/1; hedef 0 ise izin açık olsa da çıkış sıfırdır |

Kazançlar, yük ve izin bayrağı son simülasyon adımında kullanılan ayarlardır;
aralık sınırları uygulandıktan sonra gönderilir. RPM alanları tam sayıya
kesilir; `_x10` ve `_x10000` alanları en yakın tam sayıya yuvarlanır.
Hassas değerler `g_sim_state` içinde izlenebilir. `t` ve `enc_cnt` uint32
taşmasında sıfıra döner. `g_sim_state` gözlem içindir;
ayar değişiklikleri `g_sim_inputs` üzerinden yapılır. UART'tan komut alma
eklenmemiştir; bu sürüm yalnızca izleme verisi gönderir.

Simülasyon çıktısındaki enkoder ve RPM sanaldır. `HALL:` / `ENC:` fiziksel
sensör satırları yalnızca `MOTOR_SIMULATION=0` derlemesinde gönderilir.

## Model ve PID

- Sabit adım 10 ms (100 Hz); PID bu süreyi saniye cinsinden kullanır.
- Tek yönlü, birinci dereceden model: `tau*dRPM/dt = RPM_eq - RPM`.
  `tau=0.30 s`, `RPM_eq=clamp(3000*duty/100 - load_rpm, 0, 3000)`.
  Bu, gerçek bir motor için ölçülmüş elektriksel/mekanik model değildir;
  yük, tork yerine eşdeğer hız kaybı olarak temsil edilir.
- Enkoder çözünürlüğü mevcut kodla aynı: 4096 PPR × 4 = 16384 sayım/devir.
  Model hızı sanal darbelere çevrilir; PID geri beslemesi 10 ms'deki darbe
  farkından hesaplanır. Kesirli darbeler sonraki adıma taşınır.
- Çıkış %0–100 ile sınırlıdır. İntegral doygunlukta büyümeyi durdurur
  (anti-windup). Türev ölçülen hızdan alınır ve 50 ms filtre kullanır.
  `ki=0` eski integral katkısını da sıfırlar.
- Hedef ve yük aralıklarına, kazançlar 0–10 aralığına sınırlanır.
  NaN/sonsuz girişler sıfıra çevrilir. Kazançlar bu örnek model için seçilmiştir.
- Geciken döngü en çok 5 sabit adımla yetişir. Daha uzun gecikmelerde
  kalan adımlar atlanır ve `g_sim_skipped_steps` artar; sanal zaman yalnızca
  hesaplanan adımlar kadar ilerler. UART gönderim zaman aşımı 40 ms'dir;
  başarısız gönderimler `g_sim_uart_errors` ile izlenir.

`MOTOR_SIMULATION=0` derlemesi mevcut fiziksel Hall/enkoder okuma akışına
döner; bu modda da motor sürülmez ve PID uygulanmaz. Simülasyon modunda
mevcut çevre birimleri yapılandırılır ancak TIM2 enkoder sayımı başlatılmaz
ve fiziksel sensörler kontrol döngüsüne katılmaz.

## Kart olmadan test ve CSV

Proje kökünde macOS/Linux C derleyicisiyle:

```sh
cc -std=c11 -Wall -Wextra -Werror -ICore/Inc \
  Core/Src/motor_sim.c tests/test_motor_sim.c -lm -o /tmp/motor_pid_sim
/tmp/motor_pid_sim
/tmp/motor_pid_sim --csv > /tmp/motor_pid_sim.csv
```

Testler hedef takibini, yük telafisini, ulaşılamayan hedefte doygunluk ve
sonrasında toparlanmayı, durdurma/yeniden başlatmayı, düşük hızı, sayaç
taşmasını ve geçersiz girişleri kontrol eder. Test programı üretim kodundaki
aynı `MotorSim_Step` fonksiyonunu çalıştırır.

CSV demosu 24 sanal saniyeyi beklemeden hesaplar: başlangıç 1500 RPM,
4. saniyede 2200 RPM, 8. saniyede 600 RPM yük, 12. saniyede yük kaldırma,
16. saniyede 800 RPM, 20. saniyede durdurma. Bu otomatik senaryo yalnızca
`--csv` demosundadır; STM32 hedefi debugger'dan değiştirilene kadar sabittir.

`makefile.defs`, mevcut oluşturulmuş Debug makefile'larına yeni modülü bağlar.
CubeIDE kaynak listesini yenilediğinde aynı nesne dosyası ikinci kez eklenmez.
