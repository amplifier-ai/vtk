int owned_c(void);
int owned_cxx(void);
int main(void)
{
  return owned_c() == 2 && owned_cxx() == 3 ? 0 : 1;
}
