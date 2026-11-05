#include <stdio.h>
#include "hlk_protocol.h"

int main() {
  const auto result = runSelftests();
  printf("Synthetic parser/safety/command tests: %u passed, %u failed\n",
         result.passed, result.failed);
  return result.failed ? 1 : 0;
}
