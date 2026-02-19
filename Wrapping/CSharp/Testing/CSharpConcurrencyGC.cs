// SPDX-FileCopyrightText: Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
// SPDX-License-Identifier: BSD-3-Clause

// Multi-threaded stress test: concurrent creation/GC should not crash.

using System;
using System.Threading;
using System.Threading.Tasks;
using VTK;

namespace VTK.Test
{
    public class CSharpConcurrencyGC
    {
        private static volatile bool failed = false;

        public static int Main(string[] args)
        {
            try
            {
                VtkNativeLibrary.Initialize();

                int durationMs = 10000; // 10 seconds
                var cts = new CancellationTokenSource(durationMs);
                var token = cts.Token;

                // Start garbage collector on a timer
                using var gc = new VtkGarbageCollector();
                gc.SetScheduleTime(TimeSpan.FromMilliseconds(50));
                gc.Start();

                // Worker that creates and uses VTK objects
                Action workerAction = () =>
                {
                    try
                    {
                        while (!token.IsCancellationRequested && !failed)
                        {
                            var points = new vtkPoints();
                            points.InsertNextPoint(1.0, 2.0, 3.0);
                            points.InsertNextPoint(4.0, 5.0, 6.0);

                            var grid = new vtkUnstructuredGrid();
                            grid.SetPoints(points);

                            // Verify integrity
                            string className = grid.GetClassName();
                            if (className != "vtkUnstructuredGrid")
                            {
                                Console.Error.WriteLine(
                                    $"Unexpected class name: {className}");
                                failed = true;
                                return;
                            }

                            grid.Dispose();
                            points.Dispose();
                        }
                    }
                    catch (Exception ex)
                    {
                        Console.Error.WriteLine($"Worker failed: {ex}");
                        failed = true;
                    }
                };

                // Run 4 workers concurrently
                var tasks = new Task[4];
                for (int i = 0; i < tasks.Length; i++)
                {
                    tasks[i] = Task.Run(workerAction);
                }

                Task.WaitAll(tasks);

                gc.Stop();

                if (failed)
                {
                    Console.Error.WriteLine("FAIL: CSharpConcurrencyGC — concurrency error detected.");
                    return 1;
                }

                Console.WriteLine("PASS: CSharpConcurrencyGC — multi-threaded stress test passed.");
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
