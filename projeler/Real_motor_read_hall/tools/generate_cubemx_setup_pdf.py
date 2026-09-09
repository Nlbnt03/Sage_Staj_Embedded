#!/usr/bin/env python3
"""Generate the Turkish STM32/ESP32 CubeMX setup guide as an illustrated PDF."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "stm32_esp_hil_cubemx_assets"
OUTPUT = ROOT / "docs" / "STM32_ESP_HIL_CubeMX_Ayarlari.pdf"

W, H = 1240, 1754
MARGIN = 76
CONTENT_W = W - 2 * MARGIN
BOTTOM = H - 82

NAVY = "#123047"
BLUE = "#087EA4"
CYAN = "#E9F7FB"
INK = "#17232D"
MUTED = "#5B6B76"
LINE = "#CFDCE3"
WARN = "#FFF3CD"
OK = "#E8F6EE"
WHITE = "#FFFFFF"

FONT_DIR = Path("/System/Library/Fonts/Supplemental")
REGULAR = FONT_DIR / "Arial.ttf"
BOLD = FONT_DIR / "Arial Bold.ttf"
ITALIC = FONT_DIR / "Arial Italic.ttf"


def font(size, bold=False, italic=False):
    path = BOLD if bold else (ITALIC if italic else REGULAR)
    return ImageFont.truetype(str(path), size)


F_TITLE = font(50, bold=True)
F_SUBTITLE = font(25)
F_H1 = font(31, bold=True)
F_H2 = font(23, bold=True)
F_BODY = font(20)
F_BODY_BOLD = font(20, bold=True)
F_SMALL = font(16)
F_SMALL_BOLD = font(16, bold=True)
F_CODE = font(18, bold=True)


class Document:
    def __init__(self):
        self.pages = []
        self.image = None
        self.draw = None
        self.y = 0

    def new_page(self, section_title=None):
        self.image = Image.new("RGB", (W, H), WHITE)
        self.draw = ImageDraw.Draw(self.image)
        self.pages.append(self.image)
        if section_title:
            self.draw.text((MARGIN, 34), "STM32–ESP32 HIL Akım PI Simülasyonu", font=F_SMALL_BOLD, fill=NAVY)
            self.draw.text((W - MARGIN, 34), section_title, font=F_SMALL, fill=MUTED, anchor="ra")
            self.draw.line((MARGIN, 62, W - MARGIN, 62), fill=LINE, width=2)
            self.y = 88
        else:
            self.y = MARGIN

    def ensure(self, needed, section_title=None):
        if self.y + needed > BOTTOM:
            self.new_page(section_title)

    def wrapped_lines(self, text, face, width):
        words = text.split()
        if not words:
            return [""]
        lines, current = [], words[0]
        for word in words[1:]:
            trial = current + " " + word
            if self.draw.textlength(trial, font=face) <= width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def paragraph(self, text, face=F_BODY, color=INK, indent=0, gap=13, section_title=None):
        lines = self.wrapped_lines(text, face, CONTENT_W - indent)
        line_h = int(face.size * 1.38)
        self.ensure(len(lines) * line_h + gap, section_title)
        for line in lines:
            self.draw.text((MARGIN + indent, self.y), line, font=face, fill=color)
            self.y += line_h
        self.y += gap

    def heading(self, text, level=1, section_title=None):
        face = F_H1 if level == 1 else F_H2
        before = 22 if level == 1 else 13
        after = 12
        self.ensure(before + face.size * 2 + after, section_title)
        self.y += before
        self.draw.text((MARGIN, self.y), text, font=face, fill=NAVY if level == 1 else BLUE)
        self.y += int(face.size * 1.35)
        if level == 1:
            self.draw.line((MARGIN, self.y, W - MARGIN, self.y), fill=BLUE, width=3)
            self.y += after
        else:
            self.y += 5

    def box(self, title, text, kind="note", section_title=None):
        bg, accent = (CYAN, BLUE) if kind == "note" else ((WARN, "#D39B00") if kind == "warning" else (OK, "#2E9D59"))
        title_lines = self.wrapped_lines(title, F_BODY_BOLD, CONTENT_W - 42)
        body_lines = self.wrapped_lines(text, F_BODY, CONTENT_W - 42)
        line_h = 28
        height = 20 + len(title_lines) * line_h + len(body_lines) * line_h + 18
        self.ensure(height + 18, section_title)
        x0, y0, x1, y1 = MARGIN, self.y, W - MARGIN, self.y + height
        self.draw.rounded_rectangle((x0, y0, x1, y1), radius=9, fill=bg)
        self.draw.rectangle((x0, y0, x0 + 8, y1), fill=accent)
        yy = y0 + 14
        for line in title_lines:
            self.draw.text((x0 + 24, yy), line, font=F_BODY_BOLD, fill=INK)
            yy += line_h
        for line in body_lines:
            self.draw.text((x0 + 24, yy), line, font=F_BODY, fill=INK)
            yy += line_h
        self.y = y1 + 18

    def bullets(self, items, numbered=False, check=False, section_title=None):
        for idx, item in enumerate(items, 1):
            marker = f"{idx}." if numbered else ("☐" if check else "•")
            lines = self.wrapped_lines(item, F_BODY, CONTENT_W - 42)
            height = len(lines) * 28 + 9
            self.ensure(height, section_title)
            self.draw.text((MARGIN, self.y), marker, font=F_BODY_BOLD, fill=BLUE)
            yy = self.y
            for line in lines:
                self.draw.text((MARGIN + 38, yy), line, font=F_BODY, fill=INK)
                yy += 28
            self.y = yy + 9

    def formula(self, text, section_title=None):
        self.ensure(70, section_title)
        self.draw.rounded_rectangle((MARGIN, self.y, W - MARGIN, self.y + 55), radius=7, fill="#F4F7F9", outline=LINE, width=2)
        self.draw.text((W // 2, self.y + 27), text, font=F_CODE, fill=NAVY, anchor="mm")
        self.y += 73

    def table(self, headers, rows, widths=None, section_title=None):
        if widths is None:
            widths = [CONTENT_W // len(headers)] * len(headers)
            widths[-1] += CONTENT_W - sum(widths)
        x_positions = [MARGIN]
        for width in widths:
            x_positions.append(x_positions[-1] + width)

        def row_height(cells, face):
            counts = [len(self.wrapped_lines(str(cell), face, widths[i] - 18)) for i, cell in enumerate(cells)]
            return max(counts) * 23 + 18

        header_h = row_height(headers, F_SMALL_BOLD)
        self.ensure(header_h + 55, section_title)
        self._draw_table_row(headers, x_positions, widths, header_h, F_SMALL_BOLD, NAVY, WHITE)
        for row_index, row in enumerate(rows):
            h = row_height(row, F_SMALL)
            if self.y + h > BOTTOM:
                self.new_page(section_title)
                self._draw_table_row(headers, x_positions, widths, header_h, F_SMALL_BOLD, NAVY, WHITE)
            fill = "#F7FAFB" if row_index % 2 else WHITE
            self._draw_table_row(row, x_positions, widths, h, F_SMALL, fill, INK)
        self.y += 16

    def _draw_table_row(self, cells, xs, widths, height, face, fill, text_color):
        y0 = self.y
        for i, cell in enumerate(cells):
            self.draw.rectangle((xs[i], y0, xs[i + 1], y0 + height), fill=fill, outline=LINE, width=1)
            yy = y0 + 8
            for line in self.wrapped_lines(str(cell), face, widths[i] - 18):
                self.draw.text((xs[i] + 9, yy), line, font=face, fill=text_color)
                yy += 23
        self.y += height

    def screenshot(self, filename, caption, max_height=1120, section_title=None):
        source = Image.open(ASSETS / filename).convert("RGB")
        max_w = CONTENT_W
        scale = min(max_w / source.width, max_height / source.height, 1.0)
        size = (int(source.width * scale), int(source.height * scale))
        needed = size[1] + 72
        self.ensure(needed, section_title)
        resized = source.resize(size, Image.Resampling.LANCZOS)
        x = (W - size[0]) // 2
        self.image.paste(resized, (x, self.y))
        self.draw.rectangle((x, self.y, x + size[0], self.y + size[1]), outline="#A9BAC4", width=2)
        self.y += size[1] + 10
        for line in self.wrapped_lines(caption, F_SMALL, CONTENT_W):
            self.draw.text((W // 2, self.y), line, font=F_SMALL, fill=MUTED, anchor="ma")
            self.y += 22
        self.y += 18

    def finish(self):
        total = len(self.pages)
        for number, page in enumerate(self.pages, 1):
            draw = ImageDraw.Draw(page)
            draw.line((MARGIN, H - 58, W - MARGIN, H - 58), fill=LINE, width=1)
            draw.text((MARGIN, H - 43), "Real_motor_read_hall • CubeMX yapılandırma rehberi", font=F_SMALL, fill=MUTED)
            draw.text((W - MARGIN, H - 43), f"{number} / {total}", font=F_SMALL, fill=MUTED, anchor="ra")
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        self.pages[0].save(OUTPUT, "PDF", resolution=150.0, save_all=True, append_images=self.pages[1:])


def build_document():
    d = Document()

    # Cover
    d.new_page()
    d.draw.rectangle((0, 0, W, 330), fill=NAVY)
    d.draw.text((MARGIN, 92), "STM32–ESP32 HIL", font=F_TITLE, fill=WHITE)
    d.draw.text((MARGIN, 158), "Akım PI Simülasyonu", font=F_TITLE, fill=WHITE)
    d.draw.text((MARGIN, 245), "CubeMX ayarları: ne seçildi ve neden?", font=F_SUBTITLE, fill="#B9EAF7")
    d.y = 410
    d.box("Proje", "NUCLEO-G491RE / STM32G491RETx • Sistem clock 170 MHz • Kontrol frekansı 1 kHz", "note")
    d.heading("Belgenin amacı", 1)
    d.paragraph("Motor sürücüsü bağlı değilken STM32 üzerindeki akım PI yazılımını sınamak için ESP32, motorun elektriksel akım davranışını taklit eden haricî plant olarak kullanılır. Hall sensörleri ve encoder gerçek motordan okunur; yalnızca ölçülen akım ESP32 tarafından modellenir.")
    d.heading("Görev paylaşımı", 2)
    d.bullets([
        "STM32: Hall ve encoder okuma, RPM hesabı, akım PI kontrolü, duty üretimi ve UI telemetrisi.",
        "ESP32: duty + gerçek RPM + sektör bilgisinden bir sonraki modellenmiş akımı hesaplama.",
        "Desktop UI: STM32’den Hall, RPM, akım, duty ve hata sayaçlarını izleme.",
    ])
    d.formula("Hall + encoder → STM32 PI → ESP motor modeli → ölçülen akım → STM32")
    d.paragraph("Belge tarihi: 9 Eylül 2026", F_SMALL, MUTED)

    # Architecture and pins
    sec = "Amaç ve pinler"
    d.new_page(sec)
    d.heading("1. Veri akışı ve pin atamaları", 1, sec)
    d.paragraph("İki bağımsız UART seçildi. STM32–ESP32 kontrol trafiği USART1 üzerindedir; desktop UI telemetrisi LPUART1 üzerindedir. Böylece UI trafiği PI geri besleme hattından ayrılır.", section_title=sec)
    d.table(
        ["İşlev", "STM32 pini / çevrebirim", "Seçim nedeni"],
        [
            ["Hall 0/1/2", "PC0, PC1, PB0 • GPIO Input • Pull-up", "Rotorun altı geçerli elektriksel sektöründen birini belirlemek."],
            ["Encoder A/B", "PA0=TIM2_CH1, PA1=TIM2_CH2 • Pull-up", "Donanımsal quadrature konum/yön sayımı ve gerçek RPM hesabı."],
            ["Desktop UI", "PA2/PA3=LPUART1 • 4 Mbaud", "Nucleo ST-LINK Virtual COM Port üzerinden telemetri."],
            ["ESP32 HIL", "PC4/PC5=USART1 • 4 Mbaud", "Duty/RPM/sektör gönderip modellenmiş akımı geri almak."],
        ],
        [210, 375, 503], sec
    )
    d.box("Hall girişleri neden Pull-up?", "Açık-kollektör/açık-drain Hall çıkışlarında girişin boşta kararlı 1 seviyesinde kalmasını sağlar. Haricî kartın çıkış tipi ve 3.3 V uyumluluğu yine doğrulanmalıdır.", "note", sec)
    d.box("Bu aşamada komütasyon çıkışı yok", "Motor sürücüsü bağlı olmadığı için gerçek fazlara High/Low/Float uygulanmaz. Hall dizisi sektör/faz çiftini belirlemek ve telemetri üretmek için kullanılır.", "warning", sec)
    d.heading("Fiziksel STM32–ESP32 bağlantısı", 2, sec)
    d.table(
        ["STM32", "ESP32"],
        [["PC4 / USART1_TX", "UART RX (ör. GPIO16)"], ["PC5 / USART1_RX", "UART TX (ör. GPIO17)"], ["GND", "GND"]],
        [544, 544], sec
    )
    d.paragraph("TX karşı tarafın RX pinine bağlanır. Kartlar ayrı USB’den besleniyorsa iki 3V3 çıkışı birbirine bağlanmaz; yalnızca sinyal hatları ve ortak GND bağlanır.", section_title=sec)

    # First screenshots
    sec = "Pin görünümü"
    d.new_page(sec)
    d.heading("2. CubeMX pin görünümü", 1, sec)
    d.screenshot("01_gpio_uart_pins.png", "Şekil 1 — PA0/PA1 encoder ile PC4/PC5 ESP UART pinlerinin GPIO görünümü.", 720, sec)
    d.screenshot("02_pinout_overview.png", "Şekil 2 — Hall, encoder, UI LPUART ve ESP USART1 pinlerinin genel yerleşimi.", 660, sec)

    # TIM2 details
    sec = "TIM2 encoder"
    d.new_page(sec)
    d.heading("3. TIM2 — quadrature encoder", 1, sec)
    d.paragraph("Combined Channels → Encoder Mode seçildi. Remap seçenekleri farklı pin yolları içindir; PA0 ve PA1 doğrudan CH1/CH2 olduğundan sade Encoder Mode doğrudur. Index seçilmedi çünkü ayrı Z/index darbesi kullanılmıyor.", section_title=sec)
    d.table(
        ["Ayar", "Değer", "Gerekçe"],
        [
            ["Encoder Mode", "TI1 and TI2", "İki kanal ile yön ve quadrature sayım."],
            ["Prescaler", "0", "Giriş darbeleri bölünmeden sayılır."],
            ["Counter Period", "4294967295", "TIM2'nin 32 bit aralığının tamamı; seyrek taşma."],
            ["IC1 / IC2 Polarity", "Rising Edge", "Standart giriş polaritesi; yön tersse A/B veya yazılım işareti düzeltilir."],
            ["IC Selection", "Direct", "CH1 ve CH2 kendi fiziksel girişlerinden okunur."],
            ["Input Prescaler", "No division / DIV1", "Geçerli kenarlar bölünmez."],
            ["Input Filter", "6", "Çok kısa parazit darbelerini süzer; yüksek hızda gerekirse azaltılır."],
            ["Auto-reload preload", "Disable", "ARR çalışma sırasında değiştirilmiyor."],
            ["TIM2 NVIC / DMA", "Kapalı", "Sayaç 1 ms görevinde TIM2->CNT üzerinden okunacak."],
        ],
        [260, 285, 543], sec
    )
    d.formula("RPM = (Δcount × 60) / (encoder_counts_per_rev × Δt)", sec)
    d.paragraph("encoder_counts_per_rev, mekanik bir turdaki gerçek TIM2 sayım adedidir. Katalog PPR veriyorsa TI1+TI2 quadrature kullanımında çoğunlukla dört kat sayım dikkate alınır.", section_title=sec)

    # TIM2 screenshots
    sec = "TIM2 ekranları"
    d.new_page(sec)
    d.heading("4. TIM2 ekran görüntüleri", 1, sec)
    d.screenshot("03_tim2_initial.png", "Şekil 3 — PA0/PA1 atanmış, fakat çevrebirim henüz Encoder Mode olarak etkin değil.", 590, sec)
    d.screenshot("04_tim2_encoder_mode.png", "Şekil 4 — Seçilen standart Encoder Mode; remap/index seçenekleri kullanılmadı.", 785, sec)

    sec = "TIM2 filtreleri"
    d.new_page(sec)
    d.heading("5. TIM2 giriş kanalları", 1, sec)
    d.screenshot("05_tim2_filters.png", "Şekil 5 — Her iki kanal: Rising Edge, Direct, No division ve Input Filter=6.", 700, sec)
    d.box("Filtre 6 ne yapar?", "TIM2 dijital giriş filtresi, minimum süreyi sağlamayan kısa seviye değişimlerini reddeder. Gürültüyü azaltır ancak aşırı yüksek encoder frekansında gerçek darbeleri de bastırabilir. Bu yüzden maksimum motor hızında doğrulanmalıdır.", "note", sec)
    d.heading("Sayaç okuma yaklaşımı", 2, sec)
    d.bullets([
        "TIM2 donanımı A/B darbelerini CPU müdahalesi olmadan sürekli sayar.",
        "TIM6'nın her 1 ms olayında yeni sayaç ile önceki sayaç arasındaki fark alınır.",
        "32 bit unsigned fark hesabı, sayaç sarılmasını doğru biçimde karşılamalıdır.",
        "Düşük hızdaki RPM dalgalanması gerekirse zaman penceresi veya filtre ile azaltılır.",
    ], section_title=sec)

    # USART1
    sec = "USART1 HIL hattı"
    d.new_page(sec)
    d.heading("6. USART1 — STM32 ile ESP32", 1, sec)
    d.table(
        ["Ayar", "Seçim", "Gerekçe"],
        [
            ["Mode", "Asynchronous", "Ayrı clock hattı gerektirmeyen standart UART."],
            ["Baud", "4,000,000", "1 kHz paketleri düşük seri iletim gecikmesiyle taşır."],
            ["Frame", "8N1", "8 data, parity yok, 1 stop; ESP32 ile standart uyum."],
            ["Direction", "Receive and Transmit", "Komut STM→ESP, akım ESP→STM."],
            ["Flow Control", "Disable", "RTS/CTS için ilave pin kullanılmaz."],
            ["Oversampling", "16", "170 MHz UART clock ile dayanıklı örnekleme."],
            ["PC4 TX", "Very High speed", "4 Mbaud kenarlarını yeterince hızlı sürer."],
            ["PC5 RX", "Pull-up", "Karşı cihaz ayrıkken RX hattını boşta kararlı tutar."],
        ],
        [235, 285, 568], sec
    )
    d.box("Kapasite hesabı", "8N1'de bir byte yaklaşık 10 hat biti kullanır. 4 Mbaud teorik olarak yaklaşık 400 kB/s taşır. 1 ms içinde brüt yaklaşık 400 byte zaman bütçesi vardır.", "note", sec)
    d.paragraph("HIL komut/cevaplarında CRC ve sıra numarası kullanılmalıdır. Eksik veya bozuk paket modele uygulanmamalı; son geçerli paketin yaşı izlenmelidir.", section_title=sec)

    sec = "USART1 ekranı"
    d.new_page(sec)
    d.heading("7. USART1 ekran görüntüsü", 1, sec)
    d.screenshot("06_usart1.png", "Şekil 6 — USART1 Asynchronous, 4 Mbaud, 8N1, Receive and Transmit.", 1160, sec)

    # DMA and LPUART
    sec = "DMA ve UI"
    d.new_page(sec)
    d.heading("8. DMA — UART trafiğini CPU'dan ayırmak", 1, sec)
    d.table(
        ["İstek / kanal", "Ayarlar", "Rol"],
        [
            ["USART1_RX / DMA1 CH1", "Peripheral→Memory, Normal, Byte, MemInc açık, High", "ESP akım paketini RAM'e alır."],
            ["USART1_TX / DMA1 CH2", "Memory→Peripheral, Normal, Byte, MemInc açık, High", "Duty/RPM/sektör paketini yollar."],
            ["LPUART1_TX / DMA1 CH3", "Memory→Peripheral, Normal, Byte, MemInc açık, Medium", "UI telemetrisini yollar."],
        ],
        [300, 480, 308], sec
    )
    d.paragraph("Memory Increment açıktır çünkü DMA paket içindeki bir sonraki byte'a ilerler. Peripheral Increment kapalıdır çünkü UART veri register adresi sabittir. Byte alignment, 8 bit UART verisiyle eşleşir. Normal mode'da her paket bitince DMA yazılım tarafından yeniden başlatılır.", section_title=sec)
    d.heading("LPUART1 — desktop UI", 2, sec)
    d.paragraph("PA2/PA3 üzerindeki LPUART1, Nucleo ST-LINK Virtual COM Port hattıdır. UI'ye 1 kHz Hall, RPM, ölçüm akımı, PI duty ve hata sayaçları gönderilir. STM–ESP kontrol trafiğinden ayrı olduğu için UI kapalıyken de HIL döngüsü çalışabilir.", section_title=sec)
    d.box("UI bant genişliği", "Örneğin 160 byte ASCII telemetri satırı 1 kHz'de 160 kB/s veri ve yaklaşık 1.6 Mbit/s hat yükü oluşturur. 4 Mbaud içinde kalır; ikili paket daha fazla güvenlik payı sağlar.", "note", sec)

    # TIM6
    sec = "TIM6 1 kHz"
    d.new_page(sec)
    d.heading("9. TIM6 — 1 kHz kontrol zamanı", 1, sec)
    d.paragraph("TIM6 ekranında ayrı Internal Clock menüsünün görünmemesi normaldir. Activated işaretlendiğinde CubeMX iç timer clock kaynağını etkinleştirir. .ioc dosyasındaki VP_TIM6_VS_ClockSourceINT=Enable_Timer kaydı bunu doğrular.", section_title=sec)
    d.table(
        ["Ayar", "Değer", "Neden?"],
        [
            ["Activated", "Açık", "TIM6 iç zaman tabanını etkinleştirir."],
            ["Prescaler", "169", "170 MHz / (169+1) = 1 MHz sayaç clock'u."],
            ["Counter Period", "999", "1 MHz / (999+1) = 1 kHz update."],
            ["Counter Mode", "Up", "Periyodik temel sayaç."],
            ["One Pulse", "Kapalı", "Timer bir olaydan sonra durmadan sürekli çalışır."],
            ["ARR preload", "Kapalı", "Periyot çalışma sırasında değiştirilmiyor."],
            ["DMA", "Kapalı", "Timer update olayında bellek transferi yok."],
            ["NVIC", "TIM6_DAC açık", "Her 1 ms'de kontrol görevini tetikler."],
        ],
        [250, 250, 588], sec
    )
    d.formula("170,000,000 / ((169+1) × (999+1)) = 1,000 Hz = 1 ms", sec)

    sec = "TIM6 ekranı"
    d.new_page(sec)
    d.heading("10. TIM6 ekran görüntüsü", 1, sec)
    d.screenshot("07_tim6.png", "Şekil 7 — TIM6 Activated, PSC=169, ARR=999; iç clock etkinleştirme ile otomatik seçilir.", 1260, sec)

    # NVIC and tick flow
    sec = "NVIC ve çalışma sırası"
    d.new_page(sec)
    d.heading("11. NVIC öncelikleri", 1, sec)
    d.paragraph("Cortex-M'de küçük sayı daha yüksek önceliktir. Önerilen dağılım:", section_title=sec)
    d.table(
        ["Kesme", "Öncelik", "Gerekçe"],
        [
            ["TIM6_DAC", "1", "1 ms kontrol zamanını korur."],
            ["USART1 + RX/TX DMA", "2", "HIL geri beslemesi UI'den önemlidir."],
            ["LPUART1 TX DMA", "3", "UI telemetrisi kontrolü geciktirmemelidir."],
        ],
        [370, 170, 548], sec
    )
    d.box("Kaydedilmiş .ioc için son kontrol", "Belge hazırlanırken TIM6, USART1 ve DMA kesmelerinin preemption değeri dosyada hâlâ 0 görünüyordu. Bu çalışmayı tamamen engellemez; fakat amaçlanan öncelik hiyerarşisini sağlamaz. Kod üretmeden önce 1/2/3 değerlerini doğrulayın ve .ioc dosyasını kaydedin.", "warning", sec)
    d.heading("Her 1 ms'de çalışma sırası", 2, sec)
    d.bullets([
        "STM32 Hall girişlerini okur ve geçerli sektörü/faz çiftini belirler.",
        "TIM2 sayaç farkından gerçek encoder RPM'sini hesaplar.",
        "ESP32'den gelen en son geçerli modellenmiş akımı alır.",
        "Akım PI, hata üzerinden duty üretir; limit ve anti-windup uygular.",
        "STM32 duty + RPM + sektör + sıra numarasını ESP32'ye gönderir.",
        "ESP32 bir sonraki akımı hesaplayıp STM32'ye döndürür.",
        "STM32 sonuçları LPUART1 üzerinden UI'ye gönderir.",
    ], numbered=True, section_title=sec)

    # Validation and checklist
    sec = "Test kapsamı"
    d.new_page(sec)
    d.heading("12. HIL testi neyi gösterir?", 1, sec)
    d.box("Somut olarak ölçülebilecekler", "Yükselme süresi, aşım, yerleşme süresi, kalıcı hata, duty doyumu, integratör ve anti-windup davranışı, farklı RPM/akım referanslarında kararlılık, haberleşme gecikmesi, paket kaybı ve timeout güvenliği.", "success", sec)
    d.box("Bu testin kanıtlamadıkları", "Gerçek MOSFET ve gate-driver anahtarlaması, dead-time, gerçek faz akımı ripple'ı, ADC/akım sensörü doğruluğu, güç katı korumaları, EMI ve termal davranış. ESP modelinin R/L/Ke/Vbus değerleri gerçeğe yaklaştıkça sonuç daha anlamlı olur.", "warning", sec)
    d.heading("Kod üretmeden önce kontrol listesi", 2, sec)
    d.bullets([
        "PA0/PA1: TIM2 Encoder Mode, TI1+TI2, giriş filtresi 6.",
        "TIM2 PSC=0, ARR=4294967295; TIM2 NVIC ve DMA kapalı.",
        "PC4/PC5: USART1 TX/RX, 4 Mbaud, 8N1, çift yönlü.",
        "USART1 RX/TX DMA: Normal, Byte, MemInc açık, High.",
        "PA2/PA3: LPUART1 UI, 4 Mbaud; TX DMA Medium.",
        "TIM6 Activated, PSC=169, ARR=999, One Pulse kapalı.",
        "TIM6/USART1/DMA NVIC öncelikleri 1/2/3 olarak doğrulandı.",
        "Project Manager → Keep User Code when re-generating açık.",
        ".ioc kaydedildi; ardından Generate Code çalıştırılacak.",
    ], check=True, section_title=sec)
    d.paragraph("Bu belge, gönderilen yedi CubeMX ekran görüntüsü ve Real_motor_read_hall.ioc yapılandırması esas alınarak hazırlanmıştır.", F_SMALL, MUTED, section_title=sec)

    d.finish()


if __name__ == "__main__":
    build_document()
    print(OUTPUT)
