// SPDX-FileCopyrightText: Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
// SPDX-License-Identifier: BSD-3-Clause

// Test mixed GC + explicit Dispose pattern.
// Should run without crashes whether or not Dispose is called.

using System;
using VTK;

namespace VTK.Test
{
    public class CSharpGCAndDelete
    {
        public static int Main(string[] args)
        {
            try
            {
                VtkNativeLibrary.Initialize();

                int iterations = 5000;
                for (int i = 0; i < iterations; i++)
                {
                    // Pattern 1: explicit Dispose
                    var arr1 = new vtkDoubleArray();
                    arr1.SetNumberOfTuples(5);
                    arr1.Dispose();

                    // Pattern 2: let GC handle it (no Dispose)
                    var arr2 = new vtkDoubleArray();
                    arr2.SetNumberOfTuples(5);
                    // arr2 goes out of scope, GC will finalize later

                    // Periodically trigger GC sweep
                    if (i % 1000 == 0)
                    {
                        var info = vtkObjectBase.OBJECT_MANAGER.CollectGarbage(false);
                        Console.WriteLine($"  Iteration {i}: {info}");
                    }
                }

                // Final GC sweep
                var finalInfo = vtkObjectBase.OBJECT_MANAGER.CollectGarbage(true);
                Console.WriteLine($"Final: {finalInfo}");
                Console.WriteLine(finalInfo.ListKeptReferences());

                Console.WriteLine("PASS: CSharpGCAndDelete — mixed GC and Dispose works correctly.");
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
