// SPDX-FileCopyrightText: Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
// SPDX-License-Identifier: BSD-3-Clause

#include "vtkCSharpUtil.h"

#include "vtkCallbackCommand.h"
#include "vtkObject.h"
#include "vtkObjectBase.h"

#include <sstream>
#include <string>

//------------------------------------------------------------------------------
// Object lifecycle
//------------------------------------------------------------------------------

void vtkCSharp_Delete(void* obj)
{
  if (obj)
  {
    static_cast<vtkObjectBase*>(obj)->Delete();
  }
}

void vtkCSharp_Register(void* obj)
{
  if (obj)
  {
    vtkObjectBase* o = static_cast<vtkObjectBase*>(obj);
    o->Register(o);
  }
}

const char* vtkCSharp_GetClassName(void* obj)
{
  if (!obj)
  {
    return "";
  }
  return static_cast<vtkObjectBase*>(obj)->GetClassName();
}

const char* vtkCSharp_Print(void* obj)
{
  if (!obj)
  {
    return "";
  }
  static thread_local std::string result;
  std::ostringstream stream;
  static_cast<vtkObjectBase*>(obj)->Print(stream);
  result = stream.str();
  return result.c_str();
}

//------------------------------------------------------------------------------
// Observer support
//------------------------------------------------------------------------------

static void vtkCSharpCallbackBridge(
  vtkObject* vtkNotUsed(caller), unsigned long vtkNotUsed(eid), void* clientData,
  void* vtkNotUsed(calldata))
{
  VtkCSharpCallbackFunc func = reinterpret_cast<VtkCSharpCallbackFunc>(clientData);
  if (func)
  {
    func(nullptr);
  }
}

unsigned long long vtkCSharp_AddObserver(void* obj, const char* event, void* callbackPtr)
{
  if (!obj || !event)
  {
    return 0;
  }
  vtkObject* op = static_cast<vtkObject*>(obj);
  vtkCallbackCommand* cmd = vtkCallbackCommand::New();
  cmd->SetClientData(callbackPtr);
  cmd->SetCallback(vtkCSharpCallbackBridge);
  unsigned long result = op->AddObserver(event, cmd);
  cmd->Delete();
  return static_cast<unsigned long long>(result);
}

void vtkCSharp_RemoveObserver(void* obj, unsigned long long tag)
{
  if (obj)
  {
    static_cast<vtkObject*>(obj)->RemoveObserver(static_cast<unsigned long>(tag));
  }
}
