// SPDX-FileCopyrightText: Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
// SPDX-License-Identifier: BSD-3-Clause

// Point-only deformation of the dart pentagon from TestIndexBufferObjectTriangulation.

#include "vtkActor.h"
#include "vtkCallbackCommand.h"
#include "vtkCamera.h"
#include "vtkCellArray.h"
#include "vtkCommand.h"
#include "vtkNew.h"
#include "vtkObjectFactory.h"
#include "vtkOpenGLIndexBufferObject.h"
#include "vtkOpenGLPolyDataMapper.h"
#include "vtkPoints.h"
#include "vtkPolyData.h"
#include "vtkProperty.h"
#include "vtkRenderWindow.h"
#include "vtkRenderer.h"

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <vector>

namespace
{
class PolygonCacheTrackingMapper : public vtkOpenGLPolyDataMapper
{
public:
  static PolygonCacheTrackingMapper* New();
  vtkTypeMacro(PolygonCacheTrackingMapper, vtkOpenGLPolyDataMapper);
  int IndexStateChanges = 0;

protected:
  void BuildIBO(vtkRenderer* renderer, vtkActor* actor, vtkPolyData* input) override
  {
    vtkStateStorage previous;
    previous = this->IBOBuildState;
    this->Superclass::BuildIBO(renderer, actor, input);
    this->IndexStateChanges += previous != this->IBOBuildState;
  }
};
vtkStandardNewMacro(PolygonCacheTrackingMapper);

double TriangleAreaSum(vtkPoints* points, const std::vector<unsigned int>& indices)
{
  double area = 0.0;
  for (std::size_t i = 0; i + 2 < indices.size(); i += 3)
  {
    double a[3], b[3], c[3];
    points->GetPoint(indices[i], a);
    points->GetPoint(indices[i + 1], b);
    points->GetPoint(indices[i + 2], c);
    area += 0.5 * std::abs((b[0] - a[0]) * (c[1] - a[1]) -
      (b[1] - a[1]) * (c[0] - a[0]));
  }
  return area;
}

std::size_t LitPixels(const std::vector<unsigned char>& pixels)
{
  std::size_t count = 0;
  for (std::size_t i = 0; i + 3 < pixels.size(); i += 4)
  {
    count += pixels[i] != 0 || pixels[i + 1] != 0 || pixels[i + 2] != 0;
  }
  return count;
}

std::size_t DifferentPixels(const std::vector<unsigned char>& a,
  const std::vector<unsigned char>& b)
{
  if (a.size() != b.size())
  {
    return static_cast<std::size_t>(-1);
  }
  std::size_t count = 0;
  for (std::size_t i = 0; i + 3 < a.size(); i += 4)
  {
    // Compare RGB only: the contract concerns the visible polygon footprint.
    count += a[i] != b[i] || a[i + 1] != b[i + 1] || a[i + 2] != b[i + 2];
  }
  return count;
}
}

int TestMovingPolygonIndexBufferCache(int, char*[])
{
  constexpr int Width = 256;
  constexpr int Height = 256;
  int failures = 0;
  auto expect = [&failures](bool condition, const char* message)
  {
    if (!condition)
    {
      std::cerr << "FAIL: " << message << std::endl;
      ++failures;
    }
  };

  vtkNew<vtkPoints> points;
  points->SetDataTypeToDouble();
  points->InsertNextPoint(0.0, 0.0, 0.0);
  points->InsertNextPoint(4.0, 0.0, 0.0);
  points->InsertNextPoint(4.0, 4.0, 0.0);
  points->InsertNextPoint(2.0, 5.0, 0.0);
  points->InsertNextPoint(0.0, 4.0, 0.0);
  vtkNew<vtkCellArray> cells;
  const vtkIdType ids[] = { 0, 1, 2, 3, 4 };
  cells->InsertNextCell(5, ids);
  vtkNew<vtkPolyData> input;
  input->SetPoints(points);
  input->SetPolys(cells);

  std::vector<unsigned int> convexIndices;
  vtkOpenGLIndexBufferObject::AppendTriangleIndexBuffer(
    convexIndices, cells, points, 0, nullptr, nullptr);
  expect(convexIndices.size() == 9, "The convex pentagon must yield three triangles.");

  vtkNew<vtkRenderWindow> window;
  window->SetSize(Width, Height);
  window->SetMultiSamples(0);
  window->SetOffScreenRendering(1);
  vtkNew<vtkRenderer> renderer;
  renderer->SetBackground(0, 0, 0);
  window->AddRenderer(renderer);
  auto* camera = renderer->GetActiveCamera();
  camera->SetPosition(2.0, 2.5, 10.0);
  camera->SetFocalPoint(2.0, 2.5, 0.0);
  camera->SetViewUp(0.0, 1.0, 0.0);
  camera->ParallelProjectionOn();
  camera->SetParallelScale(3.0);
  camera->SetClippingRange(1.0, 20.0);
  vtkNew<PolygonCacheTrackingMapper> reusedMapper;
  reusedMapper->SetInputData(input);
  reusedMapper->ScalarVisibilityOff();
  vtkNew<vtkActor> actor;
  actor->SetMapper(reusedMapper);
  actor->GetProperty()->LightingOff();
  actor->GetProperty()->SetColor(1.0, 1.0, 1.0);
  renderer->AddActor(actor);

  vtkNew<vtkCallbackCommand> errorObserver;
  errorObserver->SetClientData(&failures);
  errorObserver->SetCallback(
    [](vtkObject*, unsigned long, void* data, void* message)
    {
      ++*static_cast<int*>(data);
      std::cerr << "VTK ErrorEvent: "
                << (message ? static_cast<const char*>(message) : "no description") << std::endl;
    });
  window->AddObserver(vtkCommand::ErrorEvent, errorObserver);
  renderer->AddObserver(vtkCommand::ErrorEvent, errorObserver);
  reusedMapper->AddObserver(vtkCommand::ErrorEvent, errorObserver);

  auto render = [&]()
  {
    window->Render();
    std::unique_ptr<unsigned char[]> pixels(
      window->GetRGBACharPixelData(0, 0, Width - 1, Height - 1, 0));
    expect(pixels != nullptr, "Pixel readback must succeed.");
    return pixels ? std::vector<unsigned char>(pixels.get(), pixels.get() + Width * Height * 4)
                  : std::vector<unsigned char>{};
  };
  const auto convexImage = render();
  expect(LitPixels(convexImage) > 0, "The initial convex polygon must be visible.");
  const int initialStateChanges = reusedMapper->IndexStateChanges;
  expect(initialStateChanges > 0, "Initial rendering must construct an index buffer.");
  const auto topologyMTime = cells->GetMTime();
  const auto oldPointsMTime = points->GetMTime();

  // Only vertex 3 moves. Cell identity, connectivity, representation and mapper settings stay fixed.
  // The resulting dart has area 10. The original fan over these new points has total area 14,
  // overlaps itself and covers the notch, so updating only the VBO cannot render it correctly.
  points->SetPoint(3, 2.0, 1.0, 0.0);
  points->Modified();
  expect(points->GetMTime() > oldPointsMTime, "The point coordinate mutation must be observable.");
  expect(cells->GetMTime() == topologyMTime, "The mutation must leave topology MTime unchanged.");
  std::vector<unsigned int> dartIndices;
  vtkOpenGLIndexBufferObject::AppendTriangleIndexBuffer(
    dartIndices, cells, points, 0, nullptr, nullptr);
  const double staleArea = TriangleAreaSum(points, convexIndices);
  const double freshArea = TriangleAreaSum(points, dartIndices);
  expect(dartIndices.size() == 9, "The dart polygon must yield three triangles.");
  expect(convexIndices != dartIndices, "Moving this vertex must require different triangle indices.");
  expect(std::abs(staleArea - 14.0) < 1e-9, "Stale triangle area must expose the invalid fan.");
  expect(std::abs(freshArea - 10.0) < 1e-9, "Fresh triangulation must cover the actual dart area.");

  const auto reusedImage = render();
  const int changedStateChanges = reusedMapper->IndexStateChanges;
  expect(LitPixels(reusedImage) > 0, "The deformed polygon must remain visible.");
  expect(DifferentPixels(convexImage, reusedImage) > 0, "The vertex mutation must change the image.");

  vtkNew<PolygonCacheTrackingMapper> freshMapper;
  freshMapper->SetInputData(input);
  freshMapper->ScalarVisibilityOff();
  freshMapper->AddObserver(vtkCommand::ErrorEvent, errorObserver);
  actor->SetMapper(freshMapper);
  const auto freshImage = render();
  const auto freshRepeatImage = render();
  expect(LitPixels(freshImage) > 0, "The independent fresh mapper must render a visible dart.");
  expect(DifferentPixels(freshImage, freshRepeatImage) == 0,
    "Repeated fresh-mapper renders must be stable before comparing the cached result.");
  actor->SetMapper(reusedMapper);
  const auto reusedAgainImage = render();
  expect(DifferentPixels(reusedImage, reusedAgainImage) == 0,
    "Swapping actor mappers must not change the reused mapper's render.");

  const auto pixelDifference = DifferentPixels(reusedImage, freshImage);
  std::cout << "NGON points_mtime_before=" << oldPointsMTime
            << " points_mtime_after=" << points->GetMTime()
            << " topology_mtime_before=" << topologyMTime
            << " topology_mtime_after=" << cells->GetMTime() << '\n';
  std::cout << "NGON initial_index_state_changes=" << initialStateChanges
            << " after_point_move=" << changedStateChanges
            << " stale_triangle_area=" << staleArea << " fresh_triangle_area=" << freshArea
            << '\n';
  std::cout << "NGON convex_lit_pixels=" << LitPixels(convexImage)
            << " reused_lit_pixels=" << LitPixels(reusedImage)
            << " fresh_lit_pixels=" << LitPixels(freshImage)
            << " reused_vs_fresh_different_pixels=" << pixelDifference << std::endl;
  expect(changedStateChanges > initialStateChanges,
    "A point mutation that changes n-gon triangulation must invalidate the index cache.");
  expect(pixelDifference == 0,
    "A reused mapper must match a fresh mapper after a point-only polygon deformation.");
  window->Finalize();
  return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
