// SPDX-FileCopyrightText: Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
// SPDX-License-Identifier: BSD-3-Clause

// Test explicit Dispose lifecycle — objects should be deterministically cleaned up.

using System;
using VTK;

namespace VTK.Test
{
    public class CSharpDelete
    {
        public static int Main(string[] args)
        {
            try
            {
                VtkNativeLibrary.Initialize();

                int iterations = 10000;
                for (int i = 0; i < iterations; i++)
                {
                    var arr = new vtkDoubleArray();
                    arr.SetNumberOfTuples(10);
                    arr.Dispose();

                    var quadric = new vtkQuadric();
                    var sample = new vtkSampleFunction();
                    sample.SetSampleDimensions(30, 30, 30);
                    sample.SetImplicitFunction(quadric);
                    sample.Dispose();
                    quadric.Dispose();
                }

                // After explicit Dispose, object manager should be mostly empty
                int remaining = vtkObjectBase.OBJECT_MANAGER.Count;
                if (remaining > 5) // small tolerance for static objects
                {
                    Console.Error.WriteLine(
                        $"FAIL: Expected object manager to be mostly empty after Dispose(), " +
                        $"but found {remaining} objects.");
                    return 1;
                }

                Console.WriteLine("PASS: CSharpDelete — explicit Dispose lifecycle works correctly.");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"FAIL: {ex}");
                return 1;
            }
        }
    }
}
