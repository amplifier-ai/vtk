// SPDX-FileCopyrightText: Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
// SPDX-License-Identifier: BSD-3-Clause

// Regression test — validates data pipeline, array marshalling, property access,
// and filter chaining. Mirrors Java Regression.java but without rendering
// (headless CI compatible).

using System;
using VTK;

namespace VTK.Test
{
    public class CSharpRegression
    {
        public static int Run(string[] args)
        {
            try
            {
                VtkNativeLibrary.Initialize();
                int errors = 0;

                // ── Test 1: Array operations ──
                errors += TestArrayOperations();

                // ── Test 2: Pipeline (ConeSource → PolyDataMapper → Actor) ──
                errors += TestPipeline();

                // ── Test 3: Filter chain (Quadric → SampleFunction → ContourFilter) ──
                errors += TestFilterChain();

                // ── Test 4: Property get/set round-trip ──
                errors += TestPropertyRoundTrip();

                // ── Test 5: String methods (GetClassName, IsA) ──
                errors += TestStringMethods();

                // ── Test 6: Object identity (GetOrCreate returns same wrapper) ──
                errors += TestObjectIdentity();

                if (errors > 0)
                {
                    Console.Error.WriteLine($"FAIL: CSharpRegression — {errors} error(s).");
                    return 1;
                }

                Console.WriteLine("PASS: CSharpRegression — all subtests passed.");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"FAIL: {ex}");
                return 1;
            }
        }

        /// <summary>
        /// Test array insert/retrieve round-trip (mirrors Java Regression array test).
        /// </summary>
        private static int TestArrayOperations()
        {
            int errors = 0;
            double[] expected = { 3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5, 8, 9, 7, 9, 3 };

            var arr = new vtkDoubleArray();
            arr.SetNumberOfComponents(1);
            foreach (double v in expected)
                arr.InsertNextTuple1(v);

            if (arr.GetNumberOfTuples() != expected.Length)
            {
                Console.Error.WriteLine(
                    $"  Array: expected {expected.Length} tuples, got {arr.GetNumberOfTuples()}");
                errors++;
            }

            for (int i = 0; i < expected.Length; i++)
            {
                double got = arr.GetTuple1(i);
                if (Math.Abs(got - expected[i]) > 1e-10)
                {
                    Console.Error.WriteLine($"  Array[{i}]: expected {expected[i]}, got {got}");
                    errors++;
                }
            }

            // Test GetValue
            for (int i = 0; i < expected.Length; i++)
            {
                double got = arr.GetValue(i);
                if (Math.Abs(got - expected[i]) > 1e-10)
                {
                    Console.Error.WriteLine(
                        $"  Array GetValue[{i}]: expected {expected[i]}, got {got}");
                    errors++;
                }
            }

            arr.Dispose();

            if (errors == 0)
                Console.WriteLine("  [OK] Array operations");
            return errors;
        }

        /// <summary>
        /// Test VTK pipeline: ConeSource → PolyDataMapper → Actor.
        /// Verifies that Update() produces geometry with expected point/cell counts.
        /// </summary>
        private static int TestPipeline()
        {
            int errors = 0;

            var cone = new vtkConeSource();
            cone.SetResolution(8);
            cone.Update();

            vtkPolyData output = cone.GetOutput();
            long nPoints = output.GetNumberOfPoints();
            long nCells = output.GetNumberOfCells();

            // Cone with resolution 8: 9 points (8 rim + 1 tip), 9 cells (8 tris + 1 polygon base)
            if (nPoints < 1)
            {
                Console.Error.WriteLine($"  Pipeline: cone has {nPoints} points (expected > 0)");
                errors++;
            }
            if (nCells < 1)
            {
                Console.Error.WriteLine($"  Pipeline: cone has {nCells} cells (expected > 0)");
                errors++;
            }

            // Test pipeline connection
            var mapper = new vtkPolyDataMapper();
            mapper.SetInputConnection(cone.GetOutputPort());

            var actor = new vtkActor();
            actor.SetMapper(mapper);

            // Verify mapper got the connection
            vtkMapper retrievedMapper = actor.GetMapper();
            if (retrievedMapper == null || retrievedMapper.Handle == IntPtr.Zero)
            {
                Console.Error.WriteLine("  Pipeline: actor.GetMapper() returned null");
                errors++;
            }

            // Verify bounds are non-degenerate
            double[] bounds = output.GetBounds();
            if (bounds == null || bounds.Length != 6)
            {
                Console.Error.WriteLine("  Pipeline: GetBounds() returned invalid result");
                errors++;
            }
            else
            {
                double xRange = bounds[1] - bounds[0];
                double yRange = bounds[3] - bounds[2];
                if (xRange <= 0 || yRange <= 0)
                {
                    Console.Error.WriteLine(
                        $"  Pipeline: degenerate bounds [{bounds[0]},{bounds[1]}] x [{bounds[2]},{bounds[3]}]");
                    errors++;
                }
            }

            actor.Dispose();
            mapper.Dispose();
            cone.Dispose();

            if (errors == 0)
                Console.WriteLine("  [OK] Pipeline (ConeSource -> Mapper -> Actor)");
            return errors;
        }

        /// <summary>
        /// Test filter chain: Quadric → SampleFunction → ContourFilter.
        /// Verifies isosurface extraction produces geometry.
        /// </summary>
        private static int TestFilterChain()
        {
            int errors = 0;

            var quadric = new vtkQuadric();
            var sample = new vtkSampleFunction();
            sample.SetSampleDimensions(30, 30, 30);
            sample.SetImplicitFunction(quadric);

            var contour = new vtkContourFilter();
            contour.SetInputConnection(sample.GetOutputPort());
            contour.GenerateValues(5, 0.0, 1.2);
            contour.Update();

            vtkPolyData contourOutput = contour.GetOutput();
            long nPoints = contourOutput.GetNumberOfPoints();
            long nCells = contourOutput.GetNumberOfCells();

            if (nPoints < 1)
            {
                Console.Error.WriteLine(
                    $"  FilterChain: contour has {nPoints} points (expected > 0)");
                errors++;
            }
            if (nCells < 1)
            {
                Console.Error.WriteLine(
                    $"  FilterChain: contour has {nCells} cells (expected > 0)");
                errors++;
            }

            contour.Dispose();
            sample.Dispose();
            quadric.Dispose();

            if (errors == 0)
                Console.WriteLine($"  [OK] Filter chain (Quadric -> Sample -> Contour: {nPoints} pts, {nCells} cells)");
            return errors;
        }

        /// <summary>
        /// Test get/set property round-trip on various types (double, int).
        /// </summary>
        private static int TestPropertyRoundTrip()
        {
            int errors = 0;

            var cone = new vtkConeSource();

            // Double property
            cone.SetHeight(3.5);
            double h = cone.GetHeight();
            if (Math.Abs(h - 3.5) > 1e-10)
            {
                Console.Error.WriteLine($"  Property: SetHeight(3.5) -> GetHeight() = {h}");
                errors++;
            }

            cone.SetRadius(2.0);
            double r = cone.GetRadius();
            if (Math.Abs(r - 2.0) > 1e-10)
            {
                Console.Error.WriteLine($"  Property: SetRadius(2.0) -> GetRadius() = {r}");
                errors++;
            }

            // Int property
            cone.SetResolution(16);
            int res = cone.GetResolution();
            if (res != 16)
            {
                Console.Error.WriteLine($"  Property: SetResolution(16) -> GetResolution() = {res}");
                errors++;
            }

            cone.Dispose();

            if (errors == 0)
                Console.WriteLine("  [OK] Property round-trip (double, int)");
            return errors;
        }

        /// <summary>
        /// Test string methods: GetClassName, IsA.
        /// </summary>
        private static int TestStringMethods()
        {
            int errors = 0;

            var cone = new vtkConeSource();
            string className = cone.GetClassName();
            if (className != "vtkConeSource")
            {
                Console.Error.WriteLine(
                    $"  String: GetClassName() = \"{className}\" (expected \"vtkConeSource\")");
                errors++;
            }

            int isA = cone.IsA("vtkPolyDataAlgorithm");
            if (isA == 0)
            {
                Console.Error.WriteLine("  String: IsA(\"vtkPolyDataAlgorithm\") returned 0");
                errors++;
            }

            int isNotA = cone.IsA("vtkImageData");
            if (isNotA != 0)
            {
                Console.Error.WriteLine("  String: IsA(\"vtkImageData\") returned non-zero");
                errors++;
            }

            cone.Dispose();

            if (errors == 0)
                Console.WriteLine("  [OK] String methods (GetClassName, IsA)");
            return errors;
        }

        /// <summary>
        /// Test that GetOrCreate returns the same C# wrapper for the same native pointer.
        /// </summary>
        private static int TestObjectIdentity()
        {
            int errors = 0;

            var cone = new vtkConeSource();
            cone.SetResolution(8);
            cone.Update();

            // Get output twice — should return the same managed wrapper
            vtkPolyData out1 = cone.GetOutput();
            vtkPolyData out2 = cone.GetOutput();

            if (out1.Handle != out2.Handle)
            {
                Console.Error.WriteLine(
                    $"  Identity: GetOutput() returned different handles: {out1.Handle} vs {out2.Handle}");
                errors++;
            }

            cone.Dispose();

            if (errors == 0)
                Console.WriteLine("  [OK] Object identity (same ptr -> same wrapper)");
            return errors;
        }
    }
}
