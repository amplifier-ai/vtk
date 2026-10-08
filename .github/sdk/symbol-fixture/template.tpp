template <class T> T template_value(T value)
{
  return value * 7;
}
template int template_value<int>(int);
