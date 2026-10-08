extern "C" int owned_c(void);
extern "C" int native_helper(void)
{
  return owned_c();
}
