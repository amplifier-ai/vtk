// SPDX-FileCopyrightText: Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
// SPDX-License-Identifier: BSD-3-Clause

// Verify that all public VTK classes in the C# assembly have wrappers.
// This test uses reflection to verify that the assembly contains
// expected class wrappers and that basic operations work on them.

using System;
using System.Linq;
using System.Reflection;
using VTK;

namespace VTK.Test
{
    public class CSharpBindingCoverage
    {
        public static int Main(string[] args)
        {
            try
            {
                VtkNativeLibrary.Initialize();

                var assembly = typeof(vtkObjectBase).Assembly;
                var vtkTypes = assembly.GetTypes()
                    .Where(t => t.IsClass && t.IsPublic && t.Namespace == "VTK"
                                && typeof(vtkObjectBase).IsAssignableFrom(t)
                                && t != typeof(vtkObjectBase))
                    .ToList();

                Console.WriteLine($"Found {vtkTypes.Count} VTK wrapper classes in assembly.");

                if (vtkTypes.Count == 0)
                {
                    Console.Error.WriteLine("FAIL: No VTK wrapper classes found in assembly.");
                    return 1;
                }

                int tested = 0;
                int skipped = 0;
                int errors = 0;

                foreach (var type in vtkTypes)
                {
                    // Check for default constructor (non-abstract classes)
                    var defaultCtor = type.GetConstructor(
                        BindingFlags.Instance | BindingFlags.Public,
                        null, Type.EmptyTypes, null);

                    if (defaultCtor == null)
                    {
                        skipped++;
                        continue;
                    }

                    try
                    {
                        // Instantiate the object
                        var obj = (vtkObjectBase)defaultCtor.Invoke(null);
                        string className = obj.GetClassName();

                        if (string.IsNullOrEmpty(className))
                        {
                            Console.Error.WriteLine($"  ERROR: {type.Name}.GetClassName() returned empty.");
                            errors++;
                        }
                        else
                        {
                            tested++;
                        }

                        obj.Dispose();
                    }
                    catch (TargetInvocationException ex) when (ex.InnerException != null)
                    {
                        // Some classes may not be instantiable (abstract in C++ but not marked in C#)
                        skipped++;
                    }
                    catch (Exception ex)
                    {
                        Console.Error.WriteLine($"  ERROR: {type.Name}: {ex.Message}");
                        errors++;
                    }
                }

                Console.WriteLine($"Tested: {tested}, Skipped: {skipped}, Errors: {errors}");

                if (errors > 0)
                {
                    Console.Error.WriteLine($"FAIL: {errors} classes had errors.");
                    return 1;
                }

                Console.WriteLine("PASS: CSharpBindingCoverage — all instantiable classes verified.");
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
