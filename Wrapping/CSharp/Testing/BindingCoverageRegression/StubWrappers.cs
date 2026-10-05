// SPDX-FileCopyrightText: Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
// SPDX-License-Identifier: BSD-3-Clause

// Deliberately isolated from the real VTK assembly: exercise the coverage runner's
// reflection, reporting and cleanup without loading or building native libraries.

using System;
using VTK.Test;

namespace VTK
{
    public static class VtkNativeLibrary
    {
        public static void Initialize() { }
    }

    public class vtkObjectBase : IDisposable
    {
        public string GetClassName()
        {
            if (this is vtkDoubleArrayClassNameFault)
            {
                switch (CoverageScenario.Failure)
                {
                    case Failure.NativeLoad:
                        throw new DllNotFoundException("synthetic native load failure");
                    case Failure.EmptyClassName:
                        return string.Empty;
                    case Failure.NullClassName:
                        return null;
                    case Failure.ClassName:
                    case Failure.ClassNameAndDisposal:
                        throw new InvalidOperationException("synthetic class name failure");
                }
            }
            return GetType().Name;
        }

        public void Dispose()
        {
            CoverageScenario.DisposalAttempts.Add(GetType().Name);
            if (this is vtkDoubleArrayClassNameFault
                && (CoverageScenario.Failure == Failure.Disposal || CoverageScenario.Failure == Failure.ClassNameAndDisposal))
            {
                throw new InvalidOperationException("synthetic disposal failure");
            }
        }
    }

    public class vtkPointsSuccess : vtkObjectBase { }

    public class vtkIntArrayConstructorFault : vtkObjectBase
    {
        public vtkIntArrayConstructorFault()
        {
            if (CoverageScenario.Failure == Failure.Constructor)
            {
                throw new InvalidOperationException("synthetic constructor failure");
            }
            if (CoverageScenario.Failure == Failure.ConstructorNativeLoad)
            {
                throw new DllNotFoundException("synthetic constructor native load failure");
            }
        }
    }

    public class vtkDoubleArrayClassNameFault : vtkObjectBase { }

    public abstract class vtkFloatArrayAbstract : vtkObjectBase
    {
        protected vtkFloatArrayAbstract() { }
    }

    public class vtkStringArrayNoDefault : vtkObjectBase
    {
        public vtkStringArrayNoDefault(int unused) { }
    }

    public class vtkPointsMapperUnsafe : vtkObjectBase
    {
        public vtkPointsMapperUnsafe() => throw new InvalidOperationException("Unsafe wrapper must be excluded");
    }

    public class vtkUnsupportedUnsafe : vtkObjectBase
    {
        public vtkUnsupportedUnsafe() => throw new InvalidOperationException("Unselected wrapper must be excluded");
    }
}
