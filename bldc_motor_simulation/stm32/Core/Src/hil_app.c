/**
 * hil_app.c  --  STM32 tarafi HIL uygulamasi (NUCLEO-G491)
 *
 * Veri akisi:
 *
 *   PC(UI: bldc_desktop)  <--LPUART1-- STM32 <--USART1--> PC(HIL: hil_server)
 *        DATA t=... text                      binary A5 5A ... CRC
 *
 *   MODEL (PC) -> FB cercevesi -> STM32 -> hall/akim/rpm -> PI -> CMD -> MODEL
 *   MODEL verisi -> HilApp_SendTelemetry() -> UI'ya text satir
 *
 * NOT: Bu satir, UI'nin telemetry.py icindeki _CURRENT_PI_TELEMETRY_RE regexine
 * birebir uyacak sekilde uretilir. Ekstra alan EKLEMEYIN (regex fullmatch).
 */
#include "hil_app.h"
#include <stdio.h>
#include <string.h>

/* ---- PI akim kontrolcusu (anti-windup, back-calculation) ----------------- */
typedef struct {
    float kp, ki, ts;
    float integ;
    float out_min, out_max;
    float u;
} hil_pi_t;

static void pi_reset(hil_pi_t *c) { c->integ = 0.0f; c->u = 0.0f; }

static float pi_step(hil_pi_t *c, float ref, float meas)
{
    float e = ref - meas;
    float u;
    c->integ += c->ki * e * c->ts;
    u = c->kp * e + c->integ;
    if (u > c->out_max) { c->integ -= (u - c->out_max); u = c->out_max; }
    else if (u < c->out_min) { c->integ -= (u - c->out_min); u = c->out_min; }
    c->u = u;
    return u;
}

/* ---- hall'dan UI sektor/high/low/valid cikarimi --------------------------
 * UI'nin current_pi_sim.c'deki CurrentPi_DecodeHall tablosuyla birebir ayni:
 *   index = hall & 0x07, degerler tablo[hall]
 */
typedef enum { HIL_PH_NONE = 0, HIL_PH_A, HIL_PH_B, HIL_PH_C } hil_phase_t;

typedef struct {
    uint8_t     sector;
    hil_phase_t high;
    hil_phase_t low;
    hil_phase_t floating;
    uint8_t     valid;
} hil_comm_t;

static const hil_comm_t k_comm_table[8] = {
    {0, HIL_PH_NONE, HIL_PH_NONE, HIL_PH_NONE, 0},
    {1, HIL_PH_A,    HIL_PH_B,    HIL_PH_C,    1},
    {5, HIL_PH_C,    HIL_PH_A,    HIL_PH_B,    1},
    {6, HIL_PH_C,    HIL_PH_B,    HIL_PH_A,    1},
    {3, HIL_PH_B,    HIL_PH_C,    HIL_PH_A,    1},
    {2, HIL_PH_A,    HIL_PH_C,    HIL_PH_B,    1},
    {4, HIL_PH_B,    HIL_PH_A,    HIL_PH_C,    1},
    {0, HIL_PH_NONE, HIL_PH_NONE, HIL_PH_NONE, 0},
};

static const char k_phase_char[4] = "-ABC";

static hil_comm_t decode_hall(uint8_t hall)
{
    return k_comm_table[hall & 0x07u];
}

/* ---- durum --------------------------------------------------------------- */
static hil_parser_t g_parser;
static hil_pi_t     g_pi;
static uint32_t     g_seq  = 0;
static uint32_t     g_ncmd = 0;
static float        g_iref = HIL_APP_IREF;
static int          g_dir  = +1;
static bool         g_enable = true;

/* son FB verisi (telemetri icin saklanir) */
static hil_fb_t     g_fb;
static hil_comm_t   g_comm;
static float        g_i_meas = 0.0f;
static float        g_duty   = 0.0f;

static char g_tx[24];   /* HIL link CMD tamponu */

/* -------------------------------------------------------------------- HIL */
static void hil_send_cmd(uint8_t mode, uint8_t gates, float duty)
{
    uint16_t n;
    if (duty < 0.0f) duty = 0.0f;
    if (duty > 1.0f) duty = 1.0f;
    n = hil_build_cmd((uint8_t *)g_tx, ++g_seq, mode, gates,
                      (uint16_t)(duty * 10000.0f), 0, 0);
    HilLink_Uart_Write((const uint8_t *)g_tx, n);
    ++g_ncmd;
}

void HilApp_Init(void)
{
    hil_parser_init(&g_parser);
    g_pi.kp = HIL_APP_KP;
    g_pi.ki = HIL_APP_KI;
    g_pi.ts = HIL_APP_TS;
    g_pi.out_min = 0.0f;
    g_pi.out_max = HIL_APP_DUTY_MAX;
    pi_reset(&g_pi);
    memset(&g_fb, 0, sizeof(g_fb));
    g_comm = decode_hall(0);
}

void HilApp_Start(void)
{
    g_enable = true;
    hil_send_cmd(HIL_MODE_COAST, 0, 0.0f);   /* el sikismasi */
}

void HilApp_SetCurrentRef(float amps) { g_iref = amps; }
void HilApp_SetDirection(int dir)     { g_dir = (dir >= 0) ? +1 : -1; }
void HilApp_SetEnable(bool en)        { g_enable = en; if (!en) pi_reset(&g_pi); }

/* her FB cercevesi icin bir kez: PI + CMD geri gonder */
static void control_step(const hil_fb_t *fb)
{
    uint8_t gates = hil_commutate(fb->hall, g_dir);

    /* sakla: telemetri bunlari kullanacak */
    g_fb   = *fb;
    g_comm = decode_hall(fb->hall);

    if (gates == 0u || !g_enable || g_iref <= 0.0f) {
        pi_reset(&g_pi);
        g_i_meas = 0.0f;
        g_duty   = 0.0f;
        hil_send_cmd(HIL_MODE_COAST, 0, 0.0f);
        return;
    }

    g_i_meas = hil_active_current(gates, fb->ia, fb->ib, fb->ic);
    g_duty   = pi_step(&g_pi, g_iref, g_i_meas);
    hil_send_cmd(HIL_MODE_SIXSTEP, gates, g_duty);
}

void HilApp_OnHilRxByte(uint8_t b)
{
    hil_fb_t fb;
    if (hil_parser_feed(&g_parser, b, &fb))
        control_step(&fb);
}

/* ------------------------------------------------------------ telemetri
 * UI (bldc_desktop) acute ayni "DATA t=..." regexini kabul eder.
 * Alanlar ve sira birebir uyumlu OLMALIDIR:
 *   DATA t=<ms> hall=<0-7> sector=<0-6> high=<A|B|C|NONE|-> low=<A|B|C|NONE|->
 *     valid=<0|1> enc=<cnt> rpm=<rpm> iref_ma=<int> fake_i_ma=<int> err_ma=<int>
 *     duty_x10=<int> integral_x10=<int> bemf_mv=<int> applied_mv=<int>
 *     enabled=<0|1>
 * degiskenler: rpm long, enc long, akim mv, gerilim mv.            */
void HilApp_SendTelemetry(void)
{
    static char line[256];
    float ctrl_i  = 0.0f;
    float ctrl_err;
    float bemf    = g_fb.vfloat;   /* modelin yuzen faz terminal gerilimi [V] */
    float applied = 24.0f * (g_duty > 0.0f ? g_duty : 0.0f);
    int len;

    switch (g_comm.high) {
    case HIL_PH_A: ctrl_i = g_fb.ia; break;
    case HIL_PH_B: ctrl_i = g_fb.ib; break;
    case HIL_PH_C: ctrl_i = g_fb.ic; break;
    default:       ctrl_i = 0.0f; break;
    }
    ctrl_err = g_iref - ctrl_i;

    len = snprintf(line, sizeof(line),
        "DATA t=%lu hall=%u sector=%u high=%c low=%c valid=%u "
        "enc=%ld rpm=%ld iref_ma=%ld fake_i_ma=%ld err_ma=%ld "
        "duty_x10=%ld integral_x10=%ld bemf_mv=%ld applied_mv=%ld "
        "enabled=%lu\r\n",
        (unsigned long)(g_fb.t_us / 1000u),
        (unsigned int)(g_fb.hall & 0x07u),
        (unsigned int)g_comm.sector,
        k_phase_char[g_comm.high],
        k_phase_char[g_comm.low],
        (unsigned int)g_comm.valid,
        (long)g_fb.enc,
        (long)(g_fb.rpm),                              /* UI rpm int bekler */
        (long)(g_iref * 1000.0f),
        (long)(ctrl_i * 1000.0f),
        (long)(ctrl_err * 1000.0f),
        (long)(g_duty * 1000.0f),                      /* duty_x10 -> /10 = % */
        (long)(g_pi.integ * 1000.0f),
        (long)(bemf * 1000.0f),
        (long)(applied * 1000.0f),
        (unsigned long)(g_enable ? 1u : 0u));

    if (len > 0 && len < (int)sizeof(line))
        HilTel_Uart_Write((const uint8_t *)line, (uint16_t)len);
}

/* tanilamalar */
uint32_t HilApp_CrcErrors(void)         { return g_parser.crc_errors; }
uint32_t HilApp_FramesOk(void)          { return g_parser.frames_ok; }
uint32_t HilApp_CommandsSent(void)      { return g_ncmd; }
float    HilApp_LastMeasuredCurrent(void) { return g_i_meas; }
float    HilApp_LastDuty(void)          { return g_duty; }
