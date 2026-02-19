// SPDX-FileCopyrightText: Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
// SPDX-License-Identifier: BSD-3-Clause

using System;
using System.Runtime.InteropServices;

namespace VTK
{
    public class vtkObjectBase : IDisposable
    {
        internal static readonly VtkObjectManager OBJECT_MANAGER = new VtkObjectManager();

        private const string UtilLib = "vtkCSharp";

        [DllImport(UtilLib, CallingConvention = CallingConvention.Cdecl)]
        private static extern void vtkCSharp_Delete(IntPtr obj);

        [DllImport(UtilLib, CallingConvention = CallingConvention.Cdecl)]
        private static extern void vtkCSharp_Register(IntPtr obj);

        [DllImport(UtilLib, CallingConvention = CallingConvention.Cdecl)]
        private static extern IntPtr vtkCSharp_GetClassName(IntPtr obj);

        [DllImport(UtilLib, CallingConvention = CallingConvention.Cdecl)]
        private static extern IntPtr vtkCSharp_Print(IntPtr obj);

        private IntPtr handle;
        private bool ownsReference;
        private bool disposed;

        public IntPtr Handle
        {
            get
            {
                if (disposed)
                {
                    throw new ObjectDisposedException(GetType().Name);
                }
                return handle;
            }
        }

        protected vtkObjectBase(IntPtr ptr, bool ownsRef)
        {
            handle = ptr;
            ownsReference = ownsRef;
            if (ptr != IntPtr.Zero)
            {
                OBJECT_MANAGER.Register(ptr.ToInt64(), this);
            }
        }

        public string GetClassName()
        {
            IntPtr ptr = vtkCSharp_GetClassName(Handle);
            return Marshal.PtrToStringUTF8(ptr) ?? string.Empty;
        }

        public string Print()
        {
            IntPtr ptr = vtkCSharp_Print(Handle);
            return Marshal.PtrToStringUTF8(ptr) ?? string.Empty;
        }

        public override string ToString()
        {
            if (disposed || handle == IntPtr.Zero)
            {
                return $"{GetType().Name} (disposed)";
            }
            return Print();
        }

        public void Dispose()
        {
            Dispose(true);
            GC.SuppressFinalize(this);
        }

        protected virtual void Dispose(bool disposing)
        {
            if (!disposed)
            {
                if (handle != IntPtr.Zero && ownsReference)
                {
                    OBJECT_MANAGER.Unregister(handle.ToInt64());
                    vtkCSharp_Delete(handle);
                }
                handle = IntPtr.Zero;
                disposed = true;
            }
        }

        ~vtkObjectBase()
        {
            Dispose(false);
        }

        internal void AddReference()
        {
            if (handle != IntPtr.Zero)
            {
                vtkCSharp_Register(handle);
            }
        }

        internal static string GetClassNameFromPointer(IntPtr ptr)
        {
            IntPtr namePtr = vtkCSharp_GetClassName(ptr);
            return Marshal.PtrToStringUTF8(namePtr) ?? string.Empty;
        }
    }
}
