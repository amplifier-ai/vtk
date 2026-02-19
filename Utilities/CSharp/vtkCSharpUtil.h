// SPDX-FileCopyrightText: Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
// SPDX-License-Identifier: BSD-3-Clause

#ifndef vtkCSharpUtil_h
#define vtkCSharpUtil_h

#include "vtkCSharpModule.h"

#ifdef _WIN32
#define VTK_CSHARP_EXTERN __declspec(dllexport)
#else
#define VTK_CSHARP_EXTERN __attribute__((visibility("default")))
#endif

extern "C"
{
  // Object lifecycle management for vtkObjectBase*
  VTK_CSHARP_EXTERN void vtkCSharp_Delete(void* obj);
  VTK_CSHARP_EXTERN void vtkCSharp_Register(void* obj);
  VTK_CSHARP_EXTERN const char* vtkCSharp_GetClassName(void* obj);
  VTK_CSHARP_EXTERN const char* vtkCSharp_Print(void* obj);

  // Observer support for vtkObject*
  typedef void (*VtkCSharpCallbackFunc)(void* clientData);
  VTK_CSHARP_EXTERN unsigned long long vtkCSharp_AddObserver(
    void* obj, const char* event, void* callbackPtr);
  VTK_CSHARP_EXTERN void vtkCSharp_RemoveObserver(void* obj, unsigned long long tag);
}

#endif
// VTK-HeaderTest-Exclude: vtkCSharpUtil.h
