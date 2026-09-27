// SPDX-FileCopyrightText: Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
// SPDX-License-Identifier: BSD-3-Clause

#include "vtkActor.h"
#include "vtkCallbackCommand.h"
#include "vtkCamera.h"
#include "vtkCellArray.h"
#include "vtkCommand.h"
#include "vtkNew.h"
#include "vtkObjectFactory.h"
#include "vtkOpenGLPolyDataMapper.h"
#include "vtkPlane.h"
#include "vtkPointData.h"
#include "vtkPoints.h"
#include "vtkPolyData.h"
#include "vtkProperty.h"
#include "vtkRenderWindow.h"
#include "vtkRenderer.h"
#include "vtkSphereSource.h"
#include "vtkUnsignedCharArray.h"

#include <cstdlib>
#include <iostream>
#include <memory>
#include <vector>

namespace
{
class CacheTrackingMapper : public vtkOpenGLPolyDataMapper
{
public:
  static CacheTrackingMapper* New();
  vtkTypeMacro(CacheTrackingMapper, vtkOpenGLPolyDataMapper);
  int IndexStateChanges = 0;

protected:
  void BuildIBO(vtkRenderer* renderer, vtkActor* actor, vtkPolyData* input) override
  {
    vtkStateStorage previous;
    previous = this->IBOBuildState;
    this->Superclass::BuildIBO(renderer, actor, input);
    if (previous != this->IBOBuildState)
    {
      ++this->IndexStateChanges;
    }
  }
};
vtkStandardNewMacro(CacheTrackingMapper);
}

int TestPolyDataMapperIndexBufferCache(int, char*[])
{
  constexpr int Width = 160;
  constexpr int Height = 120;
  int failures = 0;
  auto expect = [&failures](bool condition, const char* message)
  {
    if (!condition)
    {
      std::cerr << message << std::endl;
      ++failures;
    }
  };

  vtkNew<vtkRenderWindow> window;
  window->SetSize(Width, Height);
  window->SetMultiSamples(0);
  window->SetOffScreenRendering(1);
  vtkNew<vtkRenderer> renderer;
  renderer->SetBackground(0, 0, 0);
  window->AddRenderer(renderer);
  vtkNew<vtkSphereSource> sphere;
  sphere->SetThetaResolution(64);
  sphere->SetPhiResolution(32);
  sphere->SetRadius(0.8);
  sphere->Update();
  vtkNew<vtkPolyData> input;
  input->DeepCopy(sphere->GetOutput());
  vtkNew<CacheTrackingMapper> mapper;
  mapper->SetInputData(input);
  mapper->ScalarVisibilityOff();
  vtkNew<vtkActor> actor;
  actor->SetMapper(mapper);
  actor->GetProperty()->SetColor(0.7, 0.4, 0.2);
  renderer->AddActor(actor);
  renderer->GetActiveCamera()->SetPosition(0, 0, 3);
  renderer->GetActiveCamera()->SetFocalPoint(0, 0, 0);
  renderer->ResetCameraClippingRange();

  vtkNew<vtkCallbackCommand> errorObserver;
  errorObserver->SetClientData(&failures);
  errorObserver->SetCallback(
    [](vtkObject*, unsigned long, void* data, void* message)
    {
      ++*static_cast<int*>(data);
      std::cerr << (message ? static_cast<const char*>(message) : "VTK error") << std::endl;
    });
  window->AddObserver(vtkCommand::ErrorEvent, errorObserver);
  mapper->AddObserver(vtkCommand::ErrorEvent, errorObserver);
  renderer->AddObserver(vtkCommand::ErrorEvent, errorObserver);

  auto render = [&]()
  {
    window->Render();
    std::unique_ptr<unsigned char[]> pixels(
      window->GetRGBACharPixelData(0, 0, Width - 1, Height - 1, 0));
    expect(pixels != nullptr, "Render must provide pixel readback.");
    if (!pixels)
    {
      return std::vector<unsigned char>{};
    }
    return std::vector<unsigned char>(pixels.get(), pixels.get() + Width * Height * 4);
  };
  auto litPixels = [](const std::vector<unsigned char>& pixels)
  {
    int count = 0;
    for (size_t i = 0; i < pixels.size(); i += 4)
    {
      count += pixels[i] != 0 || pixels[i + 1] != 0 || pixels[i + 2] != 0;
    }
    return count;
  };

  const auto full = render();
  expect(litPixels(full) > 0, "Unclipped geometry must be visible.");
  const int initialStateChanges = mapper->IndexStateChanges;
  vtkNew<vtkPlane> plane;
  plane->SetNormal(1, 0, 0);
  plane->SetOrigin(0, 0, 0);
  for (int i = 0; i < 8; ++i)
  {
    mapper->RemoveAllClippingPlanes();
    mapper->AddClippingPlane(plane);
    const auto clipped = render();
    expect(litPixels(clipped) > 0 && litPixels(clipped) < litPixels(full),
      "Clipping must change visible pixels without changing the input geometry.");
    mapper->RemoveAllClippingPlanes();
    expect(render() == full, "Removing clipping must restore the full image.");
  }
  expect(mapper->IndexStateChanges == initialStateChanges,
    "Clipping-only changes must not invalidate the index buffer cache.");

  auto mutate = [&](auto change, const char* message)
  {
    const auto beforeImage = render();
    const int beforeChanges = mapper->IndexStateChanges;
    change();
    const auto afterImage = render();
    expect(mapper->IndexStateChanges > beforeChanges, message);
    expect(litPixels(afterImage) > 0, "Changed geometry must remain visible.");
    expect(afterImage != beforeImage, "Geometry or presentation changes must update the image.");
  };
  mutate(
    [&]()
    {
      auto* points = input->GetPoints();
      for (vtkIdType i = 0; i < points->GetNumberOfPoints(); ++i)
      {
        double point[3];
        points->GetPoint(i, point);
        point[0] *= 0.7;
        points->SetPoint(i, point);
      }
      points->Modified();
    },
    "Changed point positions must invalidate the index cache.");
  mutate(
    [&]()
    {
      vtkNew<vtkCellArray> reduced;
      auto* cells = input->GetPolys();
      cells->InitTraversal();
      vtkIdType size;
      const vtkIdType* ids;
      int index = 0;
      while (cells->GetNextCell(size, ids))
      {
        if (++index % 3 != 0)
        {
          reduced->InsertNextCell(size, ids);
        }
      }
      input->SetPolys(reduced);
    },
    "Changed topology must invalidate the index cache.");
  mutate([&]() { actor->GetProperty()->EdgeVisibilityOn(); },
    "Surface edge visibility must invalidate the index cache.");
  mutate([&]() { actor->GetProperty()->SetRepresentationToWireframe(); },
    "Wireframe representation must invalidate the index cache.");
  mutate(
    [&]()
    {
      vtkNew<vtkUnsignedCharArray> flags;
      flags->SetNumberOfComponents(1);
      flags->SetNumberOfTuples(input->GetNumberOfPoints());
      for (vtkIdType i = 0; i < input->GetNumberOfPoints(); ++i)
      {
        flags->SetValue(i, i % 2);
      }
      input->GetPointData()->SetAttribute(flags, vtkDataSetAttributes::EDGEFLAG);
    },
    "Changed edge flags must invalidate the index cache.");
  mutate([&]() { actor->GetProperty()->SetRepresentationToPoints(); },
    "Point representation must invalidate the index cache.");
  actor->GetProperty()->SetRepresentationToSurface();
  render();
  mutate(
    [&]()
    {
      actor->GetProperty()->VertexVisibilityOn();
      actor->GetProperty()->SetVertexColor(1, 0, 1);
      actor->GetProperty()->SetPointSize(4);
    },
    "Vertex visibility must invalidate the index cache.");

  const auto beforeRelease = render();
  const int beforeReleaseChanges = mapper->IndexStateChanges;
  mapper->ReleaseGraphicsResources(window);
  expect(render() == beforeRelease, "Resource reupload must preserve the image.");
  expect(mapper->IndexStateChanges > beforeReleaseChanges,
    "Released graphics resources must be rebuilt on the next render.");
  window->Finalize();
  return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
