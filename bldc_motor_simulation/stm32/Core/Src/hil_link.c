#include "hil_link.h"
#include <string.h>

/* -------------------------------------------------------------------- CRC */
uint16_t hil_crc16(const uint8_t *d, uint16_t n, uint16_t crc)
{
    for (uint16_t i = 0; i < n; i++) {
        crc ^= (uint16_t)d[i] << 8;
        for (uint8_t b = 0; b < 8; b++)
            crc = (crc & 0x8000u) ? (uint16_t)((crc << 1) ^ 0x1021u)
                                  : (uint16_t)(crc << 1);
    }
    return crc;
}

/* ------------------------------------------------------- little-endian oku */
static inline uint16_t rd_u16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static inline uint32_t rd_u32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static inline int16_t rd_i16(const uint8_t *p) { return (int16_t)rd_u16(p); }
static inline int32_t rd_i32(const uint8_t *p) { return (int32_t)rd_u32(p); }

/* -------------------------------------------------------------- ayristirici */
enum { S_SOF0 = 0, S_SOF1, S_TYPE, S_LEN, S_PAY, S_CRC0, S_CRC1 };

void hil_parser_init(hil_parser_t *p)
{
    memset(p, 0, sizeof(*p));
    p->st = S_SOF0;
}

static void decode_fb(const uint8_t *b, hil_fb_t *o)
{
    o->seq    = rd_u32(b + 0);
    o->t_us   = rd_u32(b + 4);
    o->enc    = rd_i32(b + 8);
    o->rpm    = (float)rd_i32(b + 12) * 0.1f;
    o->hall   = b[16];
    o->flags  = b[17];
    o->ia     = (float)rd_i16(b + 18) * 0.001f;
    o->ib     = (float)rd_i16(b + 20) * 0.001f;
    o->ic     = (float)rd_i16(b + 22) * 0.001f;
    o->vbus   = (float)rd_u16(b + 24) * 0.001f;
    o->vfloat = (float)rd_i16(b + 26) * 0.001f;
    o->torque = (float)rd_i32(b + 28) * 1e-6f;
}

bool hil_parser_feed(hil_parser_t *p, uint8_t byte, hil_fb_t *out)
{
    switch (p->st) {
    case S_SOF0:
        if (byte == 0xA5u) p->st = S_SOF1;
        break;

    case S_SOF1:
        p->st = (byte == 0x5Au) ? S_TYPE : (byte == 0xA5u ? S_SOF1 : S_SOF0);
        break;

    case S_TYPE:
        p->type = byte;
        p->st = S_LEN;
        break;

    case S_LEN:
        p->len = byte;
        p->idx = 0;
        if (p->len > HIL_RXBUF) { p->crc_errors++; p->st = S_SOF0; break; }
        p->st = (p->len == 0) ? S_CRC0 : S_PAY;
        break;

    case S_PAY:
        p->buf[p->idx++] = byte;
        if (p->idx >= p->len) p->st = S_CRC0;
        break;

    case S_CRC0:
        p->crc_rx = byte;
        p->st = S_CRC1;
        break;

    case S_CRC1: {
        p->crc_rx |= (uint16_t)byte << 8;
        uint8_t hdr[2] = { p->type, p->len };
        uint16_t c = hil_crc16(hdr, 2, 0xFFFFu);
        c = hil_crc16(p->buf, p->len, c);
        p->st = S_SOF0;
        if (c != p->crc_rx) { p->crc_errors++; return false; }
        p->frames_ok++;
        if (p->type == HIL_T_FB && p->len == HIL_FB_LEN && out) {
            decode_fb(p->buf, out);
            return true;
        }
        break;
    }
    default:
        p->st = S_SOF0;
        break;
    }
    return false;
}

/* -------------------------------------------------------- komut olusturucu */
uint16_t hil_build_cmd(uint8_t *dst, uint32_t seq, uint8_t mode, uint8_t gates,
                       uint16_t duty_a, uint16_t duty_b, uint16_t duty_c)
{
    uint8_t *p = dst;
    *p++ = 0xA5u;
    *p++ = 0x5Au;
    *p++ = HIL_T_CMD;
    *p++ = HIL_CMD_LEN;
    uint8_t *pay = p;
    *p++ = (uint8_t)(seq      ); *p++ = (uint8_t)(seq >>  8);
    *p++ = (uint8_t)(seq >> 16); *p++ = (uint8_t)(seq >> 24);
    *p++ = mode;
    *p++ = gates;
    *p++ = (uint8_t)(duty_a); *p++ = (uint8_t)(duty_a >> 8);
    *p++ = (uint8_t)(duty_b); *p++ = (uint8_t)(duty_b >> 8);
    *p++ = (uint8_t)(duty_c); *p++ = (uint8_t)(duty_c >> 8);

    uint16_t c = hil_crc16(dst + 2, 2, 0xFFFFu);       /* TYPE + LEN */
    c = hil_crc16(pay, HIL_CMD_LEN, c);                /* PAYLOAD    */
    *p++ = (uint8_t)(c); *p++ = (uint8_t)(c >> 8);
    return (uint16_t)(p - dst);                        /* 18 bayt */
}

/* ------------------------------------------------------------- komutasyon */
/* hall = Ha<<2 | Hb<<1 | Hc
 * Gercek motor (current_pi_sim.c DecodeHall) ile uyumlu:
 *   1:A+B- 2:C+A- 3:C+B- 4:B+C- 5:A+C- 6:B+A-                        */
static const uint8_t k_cw[8] = {
    /*0*/ 0,
    /*1*/ HIL_AH | HIL_BL,
    /*2*/ HIL_CH | HIL_AL,
    /*3*/ HIL_CH | HIL_BL,
    /*4*/ HIL_BH | HIL_CL,
    /*5*/ HIL_AH | HIL_CL,
    /*6*/ HIL_BH | HIL_AL,
    /*7*/ 0
};
static const uint8_t k_ccw[8] = {
    0,
    HIL_BH | HIL_AL,
    HIL_AH | HIL_CL,
    HIL_BH | HIL_CL,
    HIL_CH | HIL_BL,
    HIL_CH | HIL_AL,
    HIL_AH | HIL_BL,
    0
};

uint8_t hil_commutate(uint8_t hall, int dir)
{
    return (dir >= 0) ? k_cw[hall & 7u] : k_ccw[hall & 7u];
}

float hil_active_current(uint8_t gates, float ia, float ib, float ic)
{
    if (gates & HIL_AH) return ia;
    if (gates & HIL_BH) return ib;
    if (gates & HIL_CH) return ic;
    return 0.0f;
}
