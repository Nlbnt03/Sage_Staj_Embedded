"""
bldc_model.py
=============
3-fazli BLDC motor + 3-fazli inverter (6 MOSFET) fiziksel modeli.

Modellenen davranislar
----------------------
  * Yildiz (star) bagli 3 faz elektrik dinamigi:  v_x - v_n = R*i_x + L*di_x/dt + e_x
  * Trapez back-EMF (120 duz tepe / 60 rampa), gercek BLDC gibi
  * Notr nokta (v_n) her adimda cozulur  -> yuzen fazin BEMF'i de olculebilir (sensorsuz icin)
  * Yuzen fazda body-diode serbest gecis (freewheeling) ve diyot bloklama
  * Anahtarlamali PWM (edge / center aligned) + dead-time  -> gercek akim ripple'i
  * Mekanik: J*dw/dt = Te - Bv*w - Tcoulomb - Tload  (+ opsiyonel cogging)
  * 120 derece hall sensorleri (offset ve sensor-basi montaj hatasi girilebilir)
  * Kuadratur enkoder sayaci (x4) + index
  * Akim olcum zinciri: shunt + kazanc + ADC kuantizasyon + gurultu

Isaret konvansiyonu: i_x pozitif = akim inverter terminalinden motora dogru akar.
Faz A ekseni theta_e = 0'da hizalidir.
"""

import math
from dataclasses import dataclass, field

TWO_PI = 2.0 * math.pi
PI3 = math.pi / 3.0

# --- Gate bit maskeleri (STM32 tarafiyla ayni) -----------------------------
AH, AL, BH, BL, CH, CL = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20

# --- Calisma modlari -------------------------------------------------------
MODE_COAST = 0   # tum mosfetler kapali (serbest donus)
MODE_SIXSTEP = 1   # gates maskesi + tek duty (high-side chopping)
MODE_SIXSTEP_COMP = 2   # gates maskesi + tek duty (senkron/complementary chopping)
MODE_3DUTY = 3   # 3 bacak complementary, duty_a/b/c (SVPWM, FOC icin)
MODE_BRAKE = 4   # tum low-side ON (dinamik fren)


@dataclass
class MotorParams:
    """Varsayilan degerler ~24 V, 4 kutup cifti, 4000 rpm sinifi bir hobi BLDC'sidir."""
    # --- elektrik ---
    Rs: float = 0.35        # faz direnci [ohm]  (faz-notr)
    Ls: float = 0.30e-3     # faz endüktansi (L - M) [H]
    ke: float = 0.0240      # faz back-EMF sabiti [V*s/rad_mek], tepe deger
    #   -> hat-hat BEMF tepe = 2*ke*w ,  Kt(hat) = 2*ke = 0.048 Nm/A
    pole_pairs: int = 4

    # --- mekanik ---
    J: float = 1.20e-5      # atalet [kg*m^2]
    Bv: float = 2.0e-6      # viskoz surtunme [Nm*s/rad]
    Tc: float = 0.0040      # coulomb surtunme [Nm]
    Tcog: float = 0.0000    # cogging torku genligi [Nm] (0 = kapali)
    cog_periods: int = 6    # elektriksel tur basina cogging periyodu

    # --- guc katmani ---
    Vdc: float = 24.0       # DC bara [V]
    Vd: float = 0.70        # body diode iletim gerilimi [V]
    Rds: float = 0.020      # mosfet Rds(on) [ohm]
    deadtime: float = 500e-9  # [s]

    # --- sensorler ---
    enc_lines: int = 1000   # enkoder cizgi sayisi (CPR = 4*lines)
    hall_offset_deg: float = 0.0            # elektriksel derece, global hall kaymasi
    hall_err_deg: tuple = (0.0, 0.0, 0.0)   # sensor basina montaj hatasi (elektriksel derece)

    shunt: float = 0.010    # akim shunt'u [ohm]
    amp_gain: float = 20.0  # akim yukselteci kazanci
    adc_bits: int = 12
    adc_vref: float = 3.3
    i_noise_rms: float = 0.010  # akim olcum gurultusu [A rms]

    # --- limitler ---
    i_max: float = 60.0     # sayisal koruma [A]
    w_max: float = 20000.0  # sayisal koruma [rad/s]


def trapezoid(theta_e: float) -> float:
    """Birim genlikli trapez BEMF sekil fonksiyonu (120 duz / 60 rampa)."""
    th = theta_e % TWO_PI
    if th < 2.0 * PI3:            # 0 .. 120  -> +1
        return 1.0
    elif th < math.pi:            # 120 .. 180 -> +1'den -1'e rampa
        return 1.0 - 2.0 * (th - 2.0 * PI3) / PI3
    elif th < 5.0 * PI3:          # 180 .. 300 -> -1
        return -1.0
    else:                         # 300 .. 360 -> -1'den +1'e rampa
        return -1.0 + 2.0 * (th - 5.0 * PI3) / PI3


class BLDC:
    """
    Fiziksel model. Kullanim:
        m = BLDC(MotorParams(), dt=1e-6, pwm_freq=20000)
        m.set_command(MODE_SIXSTEP, gates=AH|BL, duty=(0.4,0,0))
        m.advance(100e-6)          # 100 us ilerlet
        m.hall(), m.encoder_count(), m.measured_currents()
    """

    def __init__(self, p: MotorParams = None, dt: float = 1e-6,
                 pwm_freq: float = 20000.0, center_aligned: bool = True,
                 average_pwm: bool = False):
        self.p = p or MotorParams()
        self.dt = dt
        self.Tpwm = 1.0 / pwm_freq
        self.center_aligned = center_aligned
        # average_pwm=True: anahtarlama modellenmez, ortalama gerilim uygulanir.
        # dt'yi PWM periyoduna kadar buyutup gercek-zamanli kosmak icin kullanilir.
        self.average_pwm = average_pwm

        # --- durumlar ---
        self.t = 0.0
        self.ia = self.ib = self.ic = 0.0
        self.theta_m = 0.0        # mekanik aci [rad], sarmalanmamis
        self.omega = 0.0          # mekanik hiz [rad/s]
        self.T_load = 0.0         # sabit dis yuk torku [Nm]
        self.load_k2 = 0.0        # hiz-kareli yuk katsayisi [Nm*s^2/rad^2] (fan)
        self.lock_rotor = False   # True -> rotor kilitli (dinamometre testi)
        self.vbus = self.p.Vdc

        # --- komut ---
        self.mode = MODE_COAST
        self.gates = 0
        self.duty = [0.0, 0.0, 0.0]

        # --- yardimci ---
        self._open = [False, False, False]   # diyot bloklama durumu
        self._carrier = 0.0
        self._rng_state = 12345
        self.v_float = 0.0        # yuzen fazin terminal gerilimi (sensorsuz icin)
        self.Te = 0.0

    # ------------------------------------------------------------------ komut
    def set_command(self, mode: int, gates: int = 0, duty=(0.0, 0.0, 0.0)):
        self.mode = mode
        self.gates = gates & 0x3F
        d = list(duty) + [0.0] * (3 - len(duty))
        self.duty = [min(1.0, max(0.0, x)) for x in d[:3]]

    def set_load(self, T_load: float = None, k2: float = None, lock: bool = None):
        """T_load: sabit tork [Nm], k2: fan yuku (T = k2*w^2), lock: rotoru kilitle."""
        if T_load is not None:
            self.T_load = T_load
        if k2 is not None:
            self.load_k2 = k2
        if lock is not None:
            self.lock_rotor = lock

    # -------------------------------------------------------------- yardimci
    def _noise(self):
        # hizli LCG tabanli, ~uniform -> gauss yaklasimi (3 toplam)
        s = 0.0
        for _ in range(3):
            self._rng_state = (1103515245 * self._rng_state + 12345) & 0x7FFFFFFF
            s += self._rng_state / 0x7FFFFFFF - 0.5
        return s * 1.1547  # varyans duzeltmesi -> ~N(0,1)

    def _pwm_on(self, duty: float) -> float:
        """Bu alt-adimda high-side'in iletim orani (0..1). Anahtarlamali modda 0/1."""
        if self.average_pwm:
            return duty
        if duty <= 0.0:
            return 0.0
        if duty >= 1.0:
            return 1.0
        c = self._carrier
        if self.center_aligned:
            tri = 2.0 * c if c < 0.5 else 2.0 * (1.0 - c)
        else:
            tri = c
        return 1.0 if tri < duty else 0.0

    def _leg_state(self, idx: int):
        """
        Bir bacak icin (high_on, low_on) dondurur. Dead-time burada uygulanir.
        idx: 0=A, 1=B, 2=C
        """
        p = self.p
        hbit = (AH, BH, CH)[idx]
        lbit = (AL, BL, CL)[idx]

        if self.mode == MODE_COAST:
            return (False, False)

        if self.mode == MODE_BRAKE:
            return (False, True)

        if self.mode == MODE_3DUTY:
            on = self._pwm_on(self.duty[idx])
            if self.average_pwm:
                return ('AVG', on)
            # dead-time: gecis anlarinin yakininda iki taraf da kapali
            hi = on >= 0.5
            return (hi, not hi) if not self._in_deadtime(self.duty[idx]) else (False, False)

        # --- MODE_SIXSTEP / MODE_SIXSTEP_COMP ---
        h_en = bool(self.gates & hbit)
        l_en = bool(self.gates & lbit)
        if not h_en and not l_en:
            return (False, False)          # bu faz yuzuyor
        d = self.duty[0]                   # six-step'te tek duty kullanilir
        if h_en:
            on = self._pwm_on(d)
            if self.average_pwm:
                return ('AVG', on)
            hi = on >= 0.5
            if self.mode == MODE_SIXSTEP_COMP:
                if self._in_deadtime(d):
                    return (False, False)
                return (hi, not hi)        # senkron dogrultma
            return (hi, False)             # klasik: high chopping, off'ta diyot
        # sadece low-side aktif faz -> surekli ON
        return (False, True)

    def _in_deadtime(self, duty: float) -> bool:
        if self.p.deadtime <= 0.0 or self.average_pwm:
            return False
        frac = self.p.deadtime / self.Tpwm
        c = self._carrier
        tri = (2.0 * c if c < 0.5 else 2.0 * (1.0 - c)) if self.center_aligned else c
        return abs(tri - duty) < frac

    # ------------------------------------------------------------ tek alt-adim
    def _substep(self, dt: float):
        p = self.p
        i = [self.ia, self.ib, self.ic]
        theta_e = self.theta_m * p.pole_pairs
        f = [trapezoid(theta_e), trapezoid(theta_e - 2.0 * PI3), trapezoid(theta_e - 4.0 * PI3)]
        e = [p.ke * self.omega * fx for fx in f]

        # --- terminal gerilimleri ve driven/open siniflandirmasi ---
        v = [0.0, 0.0, 0.0]
        driven = [False, False, False]
        floating = [False, False, False]   # her iki mosfet de kapali mi
        for k in range(3):
            hi, lo = self._leg_state(k)
            if hi == 'AVG':                       # ortalama PWM modeli
                driven[k] = True
                v[k] = lo * self.vbus - i[k] * p.Rds
                continue
            if hi and lo:                          # olmamali (shoot-through)
                hi = lo = False
            if hi:
                driven[k] = True
                v[k] = self.vbus - i[k] * p.Rds
            elif lo:
                driven[k] = True
                v[k] = 0.0 - i[k] * p.Rds
            else:
                floating[k] = True
                # yuzen bacak: akim varsa body-diode iletir
                if i[k] > 1e-4:      # akim motora giriyor -> alt diyot besler
                    driven[k] = True
                    v[k] = -p.Vd
                elif i[k] < -1e-4:   # akim motordan cikiyor -> ust diyot
                    driven[k] = True
                    v[k] = self.vbus + p.Vd
                else:
                    i[k] = 0.0

        nD = sum(1 for x in driven if x)

        didt = [0.0, 0.0, 0.0]
        if nD >= 2:
            # sum(di/dt)=0 kisitindan notr gerilimi:
            acc = 0.0
            for k in range(3):
                if driven[k]:
                    acc += v[k] - p.Rs * i[k] - e[k]
            v_n = acc / nD
            for k in range(3):
                if driven[k]:
                    didt[k] = (v[k] - v_n - p.Rs * i[k] - e[k]) / p.Ls
        else:
            # 0 veya 1 bacak surulu -> akim akamaz
            v_n = -sum(e) / 3.0 + (0.0)
            for k in range(3):
                if not driven[k]:
                    i[k] = 0.0

        # yuzen faz terminal gerilimi (sensorsuz BEMF algilama icin)
        self.v_float = 0.0
        for k in range(3):
            if not driven[k]:
                self.v_float = v_n + e[k]

        # --- akim entegrasyonu + sifir gecisinde diyot bloklamasi ---
        new_i = [0.0, 0.0, 0.0]
        forced_zero = [False, False, False]
        for k in range(3):
            ni = i[k] + didt[k] * dt
            if floating[k] and (i[k] == 0.0 or ni * i[k] < 0.0):
                ni = 0.0                       # diyot bloke etti / hic akim yok
                forced_zero[k] = True
            new_i[k] = max(-p.i_max, min(p.i_max, ni))

        # KCL zorlamasi: artik akimi yalnizca hala ileten fazlara dagit
        act = [k for k in range(3) if not forced_zero[k]]
        if act:
            s = (new_i[0] + new_i[1] + new_i[2]) / len(act)
            for k in act:
                new_i[k] -= s

        self.ia, self.ib, self.ic = new_i

        # --- tork ve mekanik ---
        Te = p.ke * (f[0] * new_i[0] + f[1] * new_i[1] + f[2] * new_i[2])
        if p.Tcog != 0.0:
            Te += p.Tcog * math.sin(p.cog_periods * theta_e)
        self.Te = Te

        if self.lock_rotor:
            # dinamometre / kilitli rotor: saf elektriksel test icin
            self.omega = 0.0
        else:
            w = self.omega
            Tf = p.Bv * w + p.Tc * math.tanh(w / 0.5)
            T_ld = self.T_load + self.load_k2 * w * abs(w)   # fan/pervane tipi yuk
            dw = (Te - Tf - T_ld) / p.J
            w += dw * dt
            self.omega = max(-p.w_max, min(p.w_max, w))
            self.theta_m += self.omega * dt

        # --- PWM tasiyicisi ---
        if not self.average_pwm:
            self._carrier = (self._carrier + dt / self.Tpwm) % 1.0
        self.t += dt

    # -------------------------------------------------------------- ilerlet
    def advance(self, T: float):
        """Simulasyonu T saniye ilerlet."""
        n = int(round(T / self.dt))
        if n < 1:
            n = 1
        for _ in range(n):
            self._substep(self.dt)

    # ------------------------------------------------------------- sensorler
    # Gercek motorun hall -> komutasyon eslemesi modelinkinden farkli oldugu icin
    # modelin urettigi hall kodu, STM32/UI'nin bekledigi gercek motor koduna
    # cevrilerek raporlanir. Boylece STM32'nin hil_commutate'i (gercek motor
    # tablosu) degistirilmeden kullanilir ve dogru gate'leri uretir.
    HALL_MODEL_TO_REAL = {1: 3, 2: 6, 3: 2, 4: 5, 5: 1, 6: 4}

    def hall(self) -> int:
        """3 bit hall: bit2=Ha, bit1=Hb, bit0=Hc. Gecerli degerler 1..6.

        Donen deger gercek motorun hall konvensiyonundadir (UI/current_pi_sim
        ile uyumlu), boylece STM32 tarafindaki gercek motor komutasyon tablosu
        dogrudan kullanilabilir."""
        p = self.p
        th = self.theta_m * p.pole_pairs + math.radians(p.hall_offset_deg)
        errs = p.hall_err_deg
        h = 0
        for k, shift in enumerate((0.0, 2.0 * PI3, 4.0 * PI3)):
            a = (th - shift - math.radians(errs[k])) % TWO_PI
            bit = 1 if a < math.pi else 0
            h |= bit << (2 - k)
        return BLDC.HALL_MODEL_TO_REAL.get(h & 7, 0)

    def sector(self) -> int:
        """0..5 elektriksel sektor (hall ile birebir uyumlu)."""
        th = (self.theta_m * self.p.pole_pairs) % TWO_PI
        return int(th / PI3)

    def encoder_count(self) -> int:
        cpr = 4 * self.p.enc_lines
        return int(math.floor(self.theta_m / TWO_PI * cpr))

    def encoder_index(self) -> int:
        """Mekanik turda bir kez 1 olan index (Z) isareti."""
        frac = (self.theta_m / TWO_PI) % 1.0
        return 1 if frac < (1.0 / (4 * self.p.enc_lines)) else 0

    def rpm(self) -> float:
        return self.omega * 60.0 / TWO_PI

    def measured_currents(self):
        """ADC zincirinden gecmis (kuantize + gurultulu) faz akimlari [A]."""
        p = self.p
        lsb_v = p.adc_vref / (1 << p.adc_bits)
        lsb_i = lsb_v / (p.shunt * p.amp_gain)
        out = []
        for x in (self.ia, self.ib, self.ic):
            y = x + self._noise() * p.i_noise_rms
            out.append(round(y / lsb_i) * lsb_i)
        return out

    def state_dict(self):
        return dict(t=self.t, ia=self.ia, ib=self.ib, ic=self.ic,
                    theta_m=self.theta_m, omega=self.omega, rpm=self.rpm(),
                    Te=self.Te, hall=self.hall(), enc=self.encoder_count(),
                    v_float=self.v_float)


# --------------------------------------------------------------------------
# Hall -> komutasyon tablosu (STM32 tarafinda da ayni tablo kullanilmali)
# hall = Ha<<2 | Hb<<1 | Hc
#
# NOT: Bu tablo gercek motorun (NUCLEO-G491 firmware'deki current_pi_sim.c
# CurrentPi_DecodeHall) dogrulanmis hall -> high/low eslemesinden turetilmistir:
#   hall1: A+ B- , hall2: C+ A- , hall3: C+ B-
#   hall4: B+ C- , hall5: A+ C- , hall6: B+ A-
# degismis halde bilinen eski varsayilan duzen yerine bu kullanilir.
# --------------------------------------------------------------------------
COMMUTATION_CW = {
    1: AH | BL,   # A+ B-
    2: CH | AL,   # C+ A-
    3: CH | BL,   # C+ B-
    4: BH | CL,   # B+ C-
    5: AH | CL,   # A+ C-
    6: BH | AL,   # B+ A-
    0: 0, 7: 0,   # gecersiz hall -> tum cikislar kapali
}
COMMUTATION_CCW = {
    1: BH | AL, 2: AH | CL, 3: BH | CL,
    4: CH | BL, 5: CH | AL, 6: AH | BL,
    0: 0, 7: 0,
}


def commutate(hall: int, direction: int = 1) -> int:
    return (COMMUTATION_CW if direction >= 0 else COMMUTATION_CCW).get(hall & 7, 0)


def active_current(gates: int, ia: float, ib: float, ic: float) -> float:
    """Six-step'te DC-link akimi = pozitif surulen fazin akimi (isaretli)."""
    if gates & AH:
        return ia
    if gates & BH:
        return ib
    if gates & CH:
        return ic
    return 0.0
