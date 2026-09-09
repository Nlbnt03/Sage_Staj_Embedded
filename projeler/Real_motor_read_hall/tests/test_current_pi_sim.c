#include "current_pi_sim.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>

static void Run(CurrentPiState *state,
                const CurrentPiInputs *inputs,
                float rpm,
                uint8_t hall,
                unsigned int steps)
{
  unsigned int i;
  for (i = 0U; i < steps; ++i)
  {
    CurrentPi_Step(state, inputs, rpm, hall);
    assert(isfinite(state->fake_current_a));
    assert(isfinite(state->duty_percent));
    assert(state->fake_current_a >= 0.0f);
    assert(state->fake_current_a <= CURRENT_PI_MAX_CURRENT_A);
    assert(state->duty_percent >= 0.0f && state->duty_percent <= 100.0f);
    assert(state->integral_percent >= 0.0f && state->integral_percent <= 100.0f);
  }
}

static void TestHallTable(void)
{
  static const uint8_t sectors[8] = {0U, 1U, 5U, 6U, 3U, 2U, 4U, 0U};
  uint8_t hall;
  for (hall = 0U; hall < 8U; ++hall)
  {
    CommutationState c = CurrentPi_DecodeHall(hall);
    assert(c.sector == sectors[hall]);
    assert(c.valid == (hall != 0U && hall != 7U));
  }
}

int main(void)
{
  CurrentPiInputs inputs = CURRENT_PI_DEFAULT_INPUTS;
  CurrentPiState state;

  TestHallTable();
  CurrentPi_Init(&state);
  Run(&state, &inputs, 1500.0f, 1U, 1000U);
  assert(fabsf(state.fake_current_a - 3.0f) < 0.02f);
  assert(fabsf(state.duty_percent - 40.2f) < 0.5f);

  Run(&state, &inputs, 0.0f, 0U, 1U);
  assert(state.duty_percent == 0.0f && state.integral_percent == 0.0f);

  inputs.enabled = 0U;
  Run(&state, &inputs, 0.0f, 3U, 1U);
  assert(state.duty_percent == 0.0f);

  puts("PASS: Hall sectors, local fake-current PI, saturation, disable");
  return 0;
}
