// SPDX-FileCopyrightText: Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
// SPDX-License-Identifier: BSD-3-Clause

#include "vtkImageData.h"
#include "vtkPointData.h"
#include "vtkRenderWindow.h"
#include "vtkRenderer.h"
#include "vtkSmartPointer.h"
#include "vtkUnsignedCharArray.h"
#include "vtkWindowToImageFilter.h"

#include <cstdio>
#include <cstring>

#ifdef _WIN32
#define VTK_CSHARP_HELPER_EXPORT __declspec(dllexport)
#else
#define VTK_CSHARP_HELPER_EXPORT __attribute__((visibility("default")))
#endif

extern "C"
{

  VTK_CSHARP_HELPER_EXPORT int VtkCSharpHelper_WarmupOpenGL()
  {
    auto renderWindow = vtkSmartPointer<vtkRenderWindow>::New();
    renderWindow->SetOffScreenRendering(1);
    renderWindow->SetSize(2, 2);

    auto renderer = vtkSmartPointer<vtkRenderer>::New();
    renderWindow->AddRenderer(renderer);
    renderWindow->Render();

    auto w2i = vtkSmartPointer<vtkWindowToImageFilter>::New();
    w2i->SetInput(renderWindow);
    w2i->SetInputBufferTypeToRGB();
    w2i->ReadFrontBufferOff();
    w2i->Update();

    return 0;
  }

  VTK_CSHARP_HELPER_EXPORT int VtkCSharpHelper_GetPixels(
    void* renderWindowPtr, int width, int height, unsigned char* buffer, int bufferSize)
  {
    auto* renderWindow = static_cast<vtkRenderWindow*>(renderWindowPtr);
    if (!renderWindow || !buffer)
      return -1;

    int expectedSize = width * height * 4;
    if (bufferSize < expectedSize)
      return -2;

    fprintf(stderr, "[Helper] Render %dx%d...\n", width, height);
    fflush(stderr);
    renderWindow->Render();
    fprintf(stderr, "[Helper] Render done\n");
    fflush(stderr);

    // Try direct framebuffer read
    fprintf(stderr, "[Helper] GetRGBACharPixelData...\n");
    fflush(stderr);
    auto pixels = vtkSmartPointer<vtkUnsignedCharArray>::New();
    int ok = renderWindow->GetRGBACharPixelData(0, 0, width - 1, height - 1, 0, pixels);
    fprintf(stderr, "[Helper] GetRGBACharPixelData returned %d, tuples=%lld\n",
      ok, pixels ? pixels->GetNumberOfTuples() : -1);
    fflush(stderr);

    unsigned char* src = nullptr;
    int numPixels = width * height;

    if (ok != 0 && pixels && pixels->GetNumberOfTuples() >= numPixels)
    {
      src = pixels->GetPointer(0);
    }
    else
    {
      // Fallback: vtkWindowToImageFilter (no re-render)
      fprintf(stderr, "[Helper] Fallback to w2i...\n");
      fflush(stderr);
      auto w2i = vtkSmartPointer<vtkWindowToImageFilter>::New();
      w2i->SetInput(renderWindow);
      w2i->SetInputBufferTypeToRGBA();
      w2i->ReadFrontBufferOff();
      w2i->ShouldRerenderOff();
      w2i->Update();
      fprintf(stderr, "[Helper] w2i done\n");
      fflush(stderr);

      auto* output = w2i->GetOutput();
      if (!output)
        return -3;
      auto* scalars = output->GetPointData()->GetScalars();
      if (!scalars)
        return -4;
      auto* charArray = vtkUnsignedCharArray::SafeDownCast(scalars);
      if (!charArray)
        return -5;
      src = charArray->GetPointer(0);
    }

    if (!src)
      return -6;

    // Flip vertically
    int stride = width * 4;
    for (int y = 0; y < height; y++)
    {
      int srcRow = height - 1 - y;
      memcpy(buffer + y * stride, src + srcRow * stride, stride);
    }

    fprintf(stderr, "[Helper] Done\n");
    fflush(stderr);
    return 0;
  }
}
