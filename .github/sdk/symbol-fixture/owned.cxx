extern "C" int owned_cxx(void)
{
  volatile int value = 3;
  return value;
}
