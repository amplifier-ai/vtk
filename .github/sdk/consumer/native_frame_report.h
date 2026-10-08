#ifndef native_frame_report_h
#define native_frame_report_h

#include <cstdint>
#include <fstream>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#if defined(_WIN32)
#include <windows.h>
#include <vector>
#elif defined(__APPLE__)
#include <dlfcn.h>
#include <mach-o/loader.h>
#endif

namespace native_sdk
{
struct NativeImage
{
  std::uintptr_t base;
  std::uint64_t size;
  std::string path;
  const char* type;
};

inline NativeImage ImageForAddress(const void* address)
{
  if (!address)
  {
    throw std::runtime_error("Native probe address is null");
  }
  NativeImage image{};
#if defined(_WIN32)
  HMODULE module = nullptr;
  if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
      GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, reinterpret_cast<LPCWSTR>(address), &module))
  {
    throw std::runtime_error("Native probe address has no loaded module");
  }
  const auto* base = reinterpret_cast<const unsigned char*>(module);
  const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
  if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0)
  {
    throw std::runtime_error("Native probe module has an invalid PE header");
  }
  const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(base + dos->e_lfanew);
  if (nt->Signature != IMAGE_NT_SIGNATURE || nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC)
  {
    throw std::runtime_error("Native probe requires a 64-bit PE image");
  }
  std::vector<wchar_t> path(32768);
  const DWORD count = GetModuleFileNameW(module, path.data(), static_cast<DWORD>(path.size()));
  if (!count || count >= path.size())
  {
    throw std::runtime_error("Native probe module path is unavailable");
  }
  const int bytes = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, path.data(), count,
    nullptr, 0, nullptr, nullptr);
  if (!bytes)
  {
    throw std::runtime_error("Native probe module path is not valid Unicode");
  }
  image.path.resize(bytes);
  if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, path.data(), count,
      image.path.data(), bytes, nullptr, nullptr))
  {
    throw std::runtime_error("Native probe module path conversion failed");
  }
  image.base = reinterpret_cast<std::uintptr_t>(module);
  image.size = nt->OptionalHeader.SizeOfImage;
  image.type = "pe";
#elif defined(__APPLE__)
  Dl_info info{};
  if (!dladdr(address, &info) || !info.dli_fbase || !info.dli_fname)
  {
    throw std::runtime_error("Native probe address has no loaded module");
  }
  const auto* header = static_cast<const mach_header_64*>(info.dli_fbase);
  if (header->magic != MH_MAGIC_64)
  {
    throw std::runtime_error("Native probe requires a 64-bit Mach-O image");
  }
  const auto* cursor = reinterpret_cast<const unsigned char*>(header + 1);
  const auto* end = cursor + header->sizeofcmds;
  std::uint64_t low = std::numeric_limits<std::uint64_t>::max();
  std::uint64_t high = 0;
  for (std::uint32_t index = 0; index < header->ncmds; ++index)
  {
    if (cursor + sizeof(load_command) > end)
    {
      throw std::runtime_error("Invalid native probe load commands");
    }
    const auto* command = reinterpret_cast<const load_command*>(cursor);
    if (command->cmdsize < sizeof(load_command) || cursor + command->cmdsize > end)
    {
      throw std::runtime_error("Invalid native probe load command size");
    }
    if (command->cmd == LC_SEGMENT_64 && command->cmdsize >= sizeof(segment_command_64))
    {
      const auto* segment = reinterpret_cast<const segment_command_64*>(command);
      if (segment->initprot && segment->vmsize)
      {
        low = segment->vmaddr < low ? segment->vmaddr : low;
        const std::uint64_t segmentEnd = segment->vmaddr + segment->vmsize;
        high = segmentEnd > high ? segmentEnd : high;
      }
    }
    cursor += command->cmdsize;
  }
  image.base = reinterpret_cast<std::uintptr_t>(info.dli_fbase);
  image.size = high > low ? high - low : 0;
  image.path = info.dli_fname;
  image.type = "macho";
#else
#error Native SDK frame reporting supports Windows and macOS
#endif
  const auto value = reinterpret_cast<std::uintptr_t>(address);
  if (!image.size || value < image.base || value - image.base >= image.size)
  {
    throw std::runtime_error("Native probe address is outside its loaded image");
  }
  return image;
}

inline std::string JsonString(const std::string& value)
{
  std::ostringstream output;
  output << '"';
  for (const unsigned char byte : value)
  {
    if (byte == '"' || byte == '\\')
    {
      output << '\\' << byte;
    }
    else if (byte < 0x20)
    {
      output << "\\u" << std::hex << std::setw(4) << std::setfill('0') << static_cast<int>(byte);
    }
    else
    {
      output << byte;
    }
  }
  output << '"';
  return output.str();
}

inline void WriteNativeFrameReport(const char* path, const void* address, const char* function)
{
  static_assert(sizeof(void*) == 8);
  const NativeImage image = ImageForAddress(address);
  std::ofstream output(path);
  output << "{\n  \"schema_version\": 1,\n  \"synthetic\": true,\n"
         << "  \"probe_function\": " << JsonString(function) << ",\n"
         << "  \"instruction_addr\": \"0x" << std::hex << reinterpret_cast<std::uintptr_t>(address) << "\",\n"
         << "  \"image_addr\": \"0x" << image.base << "\",\n"
         << "  \"image_size\": " << std::dec << image.size << ",\n"
         << "  \"image_type\": " << JsonString(image.type) << ",\n"
         << "  \"module_path\": " << JsonString(image.path) << "\n}\n";
  output.close();
  if (!output)
  {
    throw std::runtime_error("Native probe report could not be written");
  }
}
}
#endif
