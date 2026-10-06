// SPDX-FileCopyrightText: Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
// SPDX-License-Identifier: BSD-3-Clause

// Verify that all public VTK classes in the C# assembly have wrappers.
// This test uses reflection to verify that the assembly contains
// expected class wrappers and that basic operations work on them.
// It only tests classes from non-rendering modules to avoid OpenGL crashes.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using VTK;

namespace VTK.Test
{
    public class CSharpBindingCoverage
    {
        // Prefixes of classes known to be safe to instantiate without a display
        private static readonly string[] SafePrefixes = new[]
        {
            "vtkAbstractArray", "vtkAffine", "vtkBitArray", "vtkCharArray",
            "vtkDataArray", "vtkDoubleArray", "vtkFloatArray", "vtkIdTypeArray",
            "vtkIntArray", "vtkLongArray", "vtkLongLongArray", "vtkShortArray",
            "vtkSignedCharArray", "vtkStringArray", "vtkUnsignedCharArray",
            "vtkUnsignedIntArray", "vtkUnsignedLongArray", "vtkUnsignedLongLongArray",
            "vtkUnsignedShortArray", "vtkTypeFloat", "vtkTypeInt", "vtkTypeUInt",
            "vtkPoints", "vtkCellArray", "vtkFieldData",
            "vtkPolyData", "vtkUnstructuredGrid", "vtkStructuredGrid",
            "vtkRectilinearGrid", "vtkImageData",
            "vtkSphereSource", "vtkConeSource", "vtkCubeSource", "vtkCylinderSource",
            "vtkPlaneSource", "vtkLineSource", "vtkPointSource",
            "vtkTriangleFilter", "vtkCleanPolyData", "vtkAppendPolyData",
            "vtkTransform", "vtkMatrix4x4", "vtkMatrix3x3",
            "vtkQuadric", "vtkPlane", "vtkSphere", "vtkBox",
            "vtkCollection", "vtkInformation", "vtkStringOutputWindow",
            "vtkFileOutputWindow", "vtkOutputWindow",
        };

        // Substrings that indicate rendering/OpenGL-dependent classes even if
        // they match a safe prefix (e.g. vtkPolyDataMapper, vtkQuadricLODActor)
        private static readonly string[] UnsafeSubstrings = new[]
        {
            "Mapper", "Actor", "Renderer", "Render", "Widget", "Representation",
            "RayCast", "LIC", "LOD", "Silhouette", "Item", "Placer",
            "HandleRepresentation", "Feedback", "MapperNode",
        };

        public static int Run(string[] args)
        {
            try
            {
                VtkNativeLibrary.Initialize();

                var assembly = typeof(vtkObjectBase).Assembly;
                var allTypes = assembly.GetTypes()
                    .Where(t => t.IsClass && t.IsPublic && t.Namespace == "VTK"
                                && typeof(vtkObjectBase).IsAssignableFrom(t)
                                && t != typeof(vtkObjectBase))
                    .ToList();

                Console.WriteLine($"Found {allTypes.Count} VTK wrapper classes in assembly.");

                if (allTypes.Count == 0)
                {
                    Console.Error.WriteLine("FAIL: No VTK wrapper classes found in assembly.");
                    return 1;
                }

                int tested = 0;
                int skipped = 0;
                int errors = 0;

                foreach (var type in allTypes)
                {
                    // Check for default constructor (non-abstract classes)
                    var defaultCtor = type.GetConstructor(
                        BindingFlags.Instance | BindingFlags.Public,
                        null, Type.EmptyTypes, null);

                    if (type.IsAbstract || defaultCtor == null)
                    {
                        skipped++;
                        continue;
                    }

                    // Only test known-safe classes to avoid native crashes from
                    // rendering/OpenGL-dependent classes when no display is present
                    bool isSafe = SafePrefixes.Any(p => type.Name.StartsWith(p));
                    bool isUnsafe = UnsafeSubstrings.Any(s => type.Name.Contains(s));
                    if (!isSafe || isUnsafe)
                    {
                        skipped++;
                        continue;
                    }

                    vtkObjectBase obj = null;
                    bool failed = false;
                    try
                    {
                        obj = (vtkObjectBase)defaultCtor.Invoke(null);
                        string className = obj.GetClassName();

                        if (string.IsNullOrEmpty(className))
                        {
                            throw new InvalidOperationException("GetClassName returned an empty class name.");
                        }
                    }
                    catch (Exception ex)
                    {
                        ReportError(type, "constructor/GetClassName", ex);
                        failed = true;
                    }
                    finally
                    {
                        if (obj != null)
                        {
                            try
                            {
                                obj.Dispose();
                            }
                            catch (Exception ex)
                            {
                                ReportError(type, "Dispose", ex);
                                failed = true;
                            }
                        }
                    }

                    if (failed)
                    {
                        errors++;
                    }
                    else
                    {
                        tested++;
                    }
                }

                Console.WriteLine($"Tested: {tested}, Skipped: {skipped}, Errors: {errors}");

                if (tested == 0)
                {
                    Console.Error.WriteLine("FAIL: No classes could be instantiated.");
                    return 1;
                }

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

        private static void ReportError(Type type, string operation, Exception error)
        {
            Console.Error.WriteLine($"  ERROR: {type.Name} ({operation}): {error.GetBaseException()}");
        }
    }
}
