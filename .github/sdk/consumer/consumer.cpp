#include <vtkVersion.h>
#include <vtkType.h>
#include <vtkNew.h>
#include <vtkIdTypeArray.h>
#include <vtkImageData.h>
#include <vtkExternalOpenGLCamera.h>
#include <vtkOpenGLGPUVolumeRayCastMapper.h>
#include <vtkNIFTIImageReader.h>
#include <vtkSMPTools.h>
#if defined(_WIN32)
#include <vtkWin32OpenGLDXRenderWindow.h>
#endif
#include <cstring>
#include <cstdlib>
#include <iostream>
#include "native_frame_report.h"

int main()
{
  static_assert(sizeof(void*) == 8);
  static_assert(sizeof(vtkIdType) == 8);
  static_assert(sizeof(vtkTypeBool) == 4);
  vtkNew<vtkIdTypeArray> ids;
  ids->InsertNextValue(vtkIdType(1) << 40);
  vtkNew<vtkImageData> image;
  image->SetDimensions(2, 2, 2);
  image->AllocateScalars(VTK_SHORT, 1);
  vtkNew<vtkExternalOpenGLCamera> camera;
  vtkNew<vtkOpenGLGPUVolumeRayCastMapper> volume;
  vtkNew<vtkNIFTIImageReader> reader;
#if defined(_WIN32)
  vtkNew<vtkWin32OpenGLDXRenderWindow> interop;
#endif
  std::cout << "runtime=" << ::GetVTKVersion() << " headers=" << vtkVersion::GetVTKVersion()
            << " smp=" << vtkSMPTools::GetBackend() << " points=" << image->GetNumberOfPoints()
            << std::endl;
  const int result = std::strcmp(::GetVTKVersion(), "9.7.1") != 0
    || std::strcmp(vtkSMPTools::GetBackend(), "Sequential") != 0
    || ids->GetValue(0) != (vtkIdType(1) << 40) || image->GetNumberOfPoints() != 8;
  const char* report = std::getenv("VTK_SENTRY_PROBE_REPORT");
  if (result == 0 && report && report[0])
  {
    try
    {
      native_sdk::WriteNativeFrameReport(report,
        reinterpret_cast<const void*>(&vtkVersion::GetVTKVersionFull),
        "vtkVersion::GetVTKVersionFull");
    }
    catch (const std::exception& error)
    {
      std::cerr << error.what() << std::endl;
      return 2;
    }
  }
  return result;
}
