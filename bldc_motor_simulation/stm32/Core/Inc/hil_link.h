/**
 * hil_link.h  --  STM32 tarafi HIL baglantisi
 *
 * PC'deki bldc modeliyle UART uzerinden konusur. Gercek motor yerine
 * bu katmandan hall / enkoder / akim okursunuz; PWM komutunuzu da gercek
 * timer yerine (veya timer'a ek olarak) buraya yazarsiniz.
 *
 * Cerceve: A5 5A | TYPE | LEN | PAYLOAD | CRC16_LO | CRC16_HI
 *          CRC16-CCITT (0x1021, init 0xFFFF), TYPE+LEN+PAYLOAD uzerinden.
 */
#ifndef HIL_LINK_H
#define HIL_LINK_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* --- gate bit maskeleri (PC modeliyle ayni) --- */
#define HIL_AH 0x01u
#define HIL_AL 0x02u
#define HIL_BH 0x04u
#define HIL_BL 0x08u
#define HIL_CH 0x10u
#define HIL_CL 0x20u

/* --- inverter modlari --- */
#define HIL_MODE_COAST         0u  /* tum mosfetler kapali            */
#define HIL_MODE_SIXSTEP       1u  /* gates + tek duty, high chopping */
#define HIL_MODE_SIXSTEP_COMP  2u  /* gates + tek duty, senkron       */
#define HIL_MODE_3DUTY         3u  /* 3 bacak complementary (FOC)     */
#define HIL_MODE_BRAKE         4u  /* tum low-side ON                 */

#define HIL_T_CMD 0x10u
#define HIL_T_FB  0x11u
#define HIL_T_CFG 0x12u

#define HIL_CMD_LEN 12u
#define HIL_FB_LEN  32u

/* PC'den gelen sensor geri beslemesi */
typedef struct {
    uint32_t seq;        /* echo edilen komut sirasi           */
    uint32_t t_us;       /* model zamani [us]                  */
    int32_t  enc;        /* enkoder sayaci (x4, sarmalanmamis) */
    float    rpm;        /* mekanik hiz                        */
    uint8_t  hall;       /* bit2=Ha bit1=Hb bit0=Hc, 1..6      */
    uint8_t  flags;      /* bit0 = enkoder index (Z)           */
    float    ia, ib, ic; /* faz akimlari [A]                   */
    float    vbus;       /* [V]                                */
    float    vfloat;     /* yuzen faz terminal gerilimi [V]    */
    float    torque;     /* [Nm] - sadece hata ayiklama icin   */
} hil_fb_t;

/* PC'ye gonderilen inverter komutu */
typedef struct {
    uint32_t seq;
    uint8_t  mode;
    uint8_t  gates;
    uint16_t duty_a;     /* 0..10000 = %0..%100 */
    uint16_t duty_b;
    uint16_t duty_c;
} hil_cmd_t;

/* --- ayristirici --- */
#define HIL_RXBUF 64
typedef struct {
    uint8_t  st;
    uint8_t  type;
    uint8_t  len;
    uint8_t  idx;
    uint8_t  buf[HIL_RXBUF];
    uint16_t crc_rx;
    uint32_t crc_errors;
    uint32_t frames_ok;
} hil_parser_t;

void     hil_parser_init(hil_parser_t *p);
/** Tek bayt besler. Gecerli bir FB cercevesi tamamlandiysa true doner ve
 *  *out doldurulur. Kesme icinden cagrilabilir. */
bool     hil_parser_feed(hil_parser_t *p, uint8_t byte, hil_fb_t *out);

/** Komut cercevesini tampona yazar, uzunlugu doner (18 bayt). */
uint16_t hil_build_cmd(uint8_t *dst, uint32_t seq, uint8_t mode, uint8_t gates,
                       uint16_t duty_a, uint16_t duty_b, uint16_t duty_c);

uint16_t hil_crc16(const uint8_t *d, uint16_t n, uint16_t crc);

/** hall (1..6) -> gate maskesi. dir >= 0 ileri, < 0 geri. */
uint8_t  hil_commutate(uint8_t hall, int dir);
/** Six-step'te olculecek akim = pozitif surulen fazin akimi. */
float    hil_active_current(uint8_t gates, float ia, float ib, float ic);

#ifdef __cplusplus
}
#endif
#endif /* HIL_LINK_H */
