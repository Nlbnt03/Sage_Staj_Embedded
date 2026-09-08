#include "motor_sim.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static void Run(MotorSimState *s, const MotorSimInputs *in, unsigned steps)
{
  for (unsigned i = 0; i < steps; ++i)
  {
    MotorSim_Step(s, in);
    assert(isfinite(s->model_rpm) && isfinite(s->measured_rpm));
    assert(isfinite(s->duty_percent) && isfinite(s->integral_percent));
    assert(s->duty_percent >= 0.0f && s->duty_percent <= 100.0f);
    assert(s->integral_percent >= 0.0f && s->integral_percent <= 100.0f);
    assert(s->model_rpm >= 0.0f && s->model_rpm <= MOTOR_SIM_MAX_RPM);
  }
}

static void CheckTracking(const MotorSimState *s, float target)
{
  if (fabsf(s->measured_rpm - target) >= 2.0f)
    fprintf(stderr, "Tracking failed at %u ms: target=%.2f measured=%.2f duty=%.2f I=%.2f\n",
            (unsigned)s->elapsed_ms, target, s->measured_rpm,
            s->duty_percent, s->integral_percent);
  assert(fabsf(s->measured_rpm - target) < 2.0f);
}

static void DemoCsv(void)
{
  MotorSimState s;
  MotorSimInputs in = MOTOR_SIM_DEFAULT_INPUTS;
  MotorSim_Init(&s);
  puts("time_ms,target_rpm,measured_rpm,model_rpm,duty_percent,load_rpm");
  for (unsigned i = 0; i < 2400; ++i)
  {
    if (i == 400) in.target_rpm = 2200.0f;
    if (i == 800) in.load_rpm = 600.0f;
    if (i == 1200) in.load_rpm = 0.0f;
    if (i == 1600) in.target_rpm = 800.0f;
    if (i == 2000) in.target_rpm = 0.0f;
    Run(&s, &in, 1);
    if (i % 10 == 9)
      printf("%u,%.3f,%.3f,%.3f,%.3f,%.3f\n", (unsigned)s.elapsed_ms,
             s.target_rpm, s.measured_rpm, s.model_rpm, s.duty_percent, in.load_rpm);
  }
}

int main(int argc, char **argv)
{
  MotorSimState s;
  MotorSimInputs in = MOTOR_SIM_DEFAULT_INPUTS;
  if (argc == 2 && strcmp(argv[1], "--csv") == 0)
  {
    DemoCsv();
    return 0;
  }

  MotorSim_Init(&s);
  Run(&s, &in, 600);
  CheckTracking(&s, 1500.0f);
  assert(fabsf(s.duty_percent - 50.0f) < 0.2f);
  in.load_rpm = 600.0f;
  Run(&s, &in, 600);
  CheckTracking(&s, 1500.0f);
  assert(fabsf(s.duty_percent - 70.0f) < 0.2f);
  in.load_rpm = 0.0f;
  in.target_rpm = 2500.0f;
  Run(&s, &in, 600);
  CheckTracking(&s, 2500.0f);
  in.target_rpm = 500.0f;
  Run(&s, &in, 600);
  CheckTracking(&s, 500.0f);

  /* Ulasilamayan hedefte doyum; sonra hedef dusunce hizla toparlama. */
  in.target_rpm = 3000.0f;
  in.load_rpm = 1000.0f;
  Run(&s, &in, 2000);
  CheckTracking(&s, 2000.0f);
  assert(s.duty_percent > 99.0f);
  in.target_rpm = 700.0f;
  Run(&s, &in, 400);
  CheckTracking(&s, 700.0f);

  in.enabled = 0;
  Run(&s, &in, 1);
  assert(s.duty_percent == 0.0f && s.integral_percent == 0.0f);
  Run(&s, &in, 600);
  CheckTracking(&s, 0.0f);
  in.enabled = 1;
  in.load_rpm = 0.0f;
  Run(&s, &in, 600);
  CheckTracking(&s, 700.0f);
  in.target_rpm = 0.0f;
  Run(&s, &in, 1);
  assert(s.duty_percent == 0.0f && s.integral_percent == 0.0f);
  Run(&s, &in, 600);
  CheckTracking(&s, 0.0f);

  in.target_rpm = 1.0f;
  Run(&s, &in, 1200);
  assert(fabsf(s.model_rpm - 1.0f) < 0.1f);
  in.target_rpm = 1500.0f;
  Run(&s, &in, 600);
  s.encoder_count = UINT32_MAX - 10U;
  s.elapsed_ms = UINT32_MAX - 5U;
  Run(&s, &in, 1);
  assert(s.encoder_count < 5000U && s.elapsed_ms == 4U);
  CheckTracking(&s, 1500.0f);

  /* P-only ve PD: integral kazanci sifirken eski I katkisi kalmamali. */
  in.ki = 0.0f;
  Run(&s, &in, 1);
  assert(s.integral_percent == 0.0f);
  in.target_rpm = -10.0f;
  Run(&s, &in, 1);
  assert(s.target_rpm == 0.0f && s.duty_percent == 0.0f);
  in.target_rpm = 9000.0f;
  Run(&s, &in, 1);
  assert(s.target_rpm == MOTOR_SIM_MAX_RPM);
  in.target_rpm = NAN;
  in.kp = INFINITY;
  in.ki = NAN;
  in.kd = -1.0f;
  in.load_rpm = NAN;
  Run(&s, &in, 100);
  assert(s.target_rpm == 0.0f && s.duty_percent == 0.0f);

  puts("PASS: tracking, load rejection, saturation recovery, stop/restart, low RPM, wrap, invalid inputs");
  return 0;
}
