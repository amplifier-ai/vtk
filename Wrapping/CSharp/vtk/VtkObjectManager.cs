// SPDX-FileCopyrightText: Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
// SPDX-License-Identifier: BSD-3-Clause

using System;
using System.Collections.Concurrent;
using System.Reflection;

namespace VTK
{
    public class VtkObjectManager
    {
        private readonly ConcurrentDictionary<long, WeakReference<vtkObjectBase>> objectMap =
            new ConcurrentDictionary<long, WeakReference<vtkObjectBase>>();

        private readonly ConcurrentDictionary<long, string> classNameMap =
            new ConcurrentDictionary<long, string>();

        public void Register(long id, vtkObjectBase obj)
        {
            objectMap[id] = new WeakReference<vtkObjectBase>(obj);
            classNameMap[id] = obj.GetClassName();
        }

        public void Unregister(long id)
        {
            objectMap.TryRemove(id, out _);
            classNameMap.TryRemove(id, out _);
        }

        public T GetOrCreate<T>(IntPtr ptr) where T : vtkObjectBase
        {
            if (ptr == IntPtr.Zero)
            {
                return null;
            }

            long id = ptr.ToInt64();

            if (objectMap.TryGetValue(id, out var weakRef) && weakRef.TryGetTarget(out var existing))
            {
                return (T)existing;
            }

            // Look up the actual VTK class name and try to instantiate the most derived C# type
            string className = vtkObjectBase.GetClassNameFromPointer(ptr);
            Type type = FindType(className);
            if (type == null)
            {
                type = typeof(T);
            }

            // Use the internal (IntPtr, bool) constructor
            var ctor = type.GetConstructor(
                BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public,
                null,
                new Type[] { typeof(IntPtr), typeof(bool) },
                null);

            if (ctor == null)
            {
                throw new InvalidOperationException(
                    $"Type {type.Name} does not have an (IntPtr, bool) constructor.");
            }

            // ownsRef = true: the managed wrapper will release this reference
            var obj = (T)ctor.Invoke(new object[] { ptr, true });
            return obj;
        }

        public VtkReferenceInformation CollectGarbage(bool debug)
        {
            GC.Collect();
            GC.WaitForPendingFinalizers();

            var info = new VtkReferenceInformation(debug);
            foreach (var kvp in objectMap)
            {
                if (kvp.Value.TryGetTarget(out _))
                {
                    classNameMap.TryGetValue(kvp.Key, out string name);
                    info.AddKeptObject(name ?? "unknown");
                }
                else
                {
                    classNameMap.TryGetValue(kvp.Key, out string name);
                    info.AddFreedObject(name ?? "unknown");
                    Unregister(kvp.Key);
                }
            }
            return info;
        }

        public int Count => objectMap.Count;

        private static Type FindType(string vtkClassName)
        {
            if (string.IsNullOrEmpty(vtkClassName))
            {
                return null;
            }

            string fullName = "VTK." + vtkClassName;

            // Search the current assembly first
            Type type = typeof(vtkObjectBase).Assembly.GetType(fullName);
            if (type != null)
            {
                return type;
            }

            // Search all loaded assemblies
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                type = asm.GetType(fullName);
                if (type != null)
                {
                    return type;
                }
            }

            return null;
        }
    }
}
