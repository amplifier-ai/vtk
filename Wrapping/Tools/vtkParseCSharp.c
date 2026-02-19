// SPDX-FileCopyrightText: Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
// SPDX-License-Identifier: BSD-3-Clause

// C# managed class generator for VTK
// Generates .cs files with [DllImport] declarations and public wrapper methods
// Modeled on vtkParseJava.c

#include "vtkParse.h"
#include "vtkParseHierarchy.h"
#include "vtkParseMain.h"
#include "vtkParseSystem.h"
#include "vtkWrap.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// NOLINTBEGIN(bugprone-unsafe-functions)

static HierarchyInfo* hierarchyInfo = NULL;
static StringCache* stringCache = NULL;
static int numberOfWrappedFunctions = 0;
static FunctionInfo* wrappedFunctions[1000];
static FunctionInfo* thisFunction;
static const char* nativeLibName = "vtkCommonCoreCSharp";

/* Output C# parameter type for public wrapper methods */
static void OutputCSharpParamType(FILE* fp, int i)
{
  unsigned int aType = (thisFunction->ArgTypes[i] & VTK_PARSE_UNQUALIFIED_TYPE);

  if (aType == VTK_PARSE_VOID)
  {
    return;
  }

  if (thisFunction->ArgTypes[i] == VTK_PARSE_FUNCTION)
  {
    fprintf(fp, "Action id0");
    return;
  }

  /* strings */
  if (aType == VTK_PARSE_CHAR_PTR || aType == VTK_PARSE_STRING || aType == VTK_PARSE_STRING_REF)
  {
    fprintf(fp, "string id%i", i);
    return;
  }

  /* object pointer */
  if (aType == VTK_PARSE_OBJECT_PTR)
  {
    fprintf(fp, "%s id%i", thisFunction->ArgClasses[i], i);
    return;
  }

  /* array types */
  if ((aType & VTK_PARSE_INDIRECT) == VTK_PARSE_POINTER && aType != VTK_PARSE_CHAR_PTR &&
    aType != VTK_PARSE_OBJECT_PTR)
  {
    switch ((aType & VTK_PARSE_BASE_TYPE) & ~VTK_PARSE_UNSIGNED)
    {
      case VTK_PARSE_FLOAT:
        fprintf(fp, "float[] id%i", i);
        return;
      case VTK_PARSE_DOUBLE:
        fprintf(fp, "double[] id%i", i);
        return;
      case VTK_PARSE_INT:
        fprintf(fp, "int[] id%i", i);
        return;
      case VTK_PARSE_SHORT:
        fprintf(fp, "short[] id%i", i);
        return;
      case VTK_PARSE_LONG:
      case VTK_PARSE_LONG_LONG:
        fprintf(fp, "long[] id%i", i);
        return;
      case VTK_PARSE_BOOL:
        fprintf(fp, "bool[] id%i", i);
        return;
      case VTK_PARSE_CHAR:
      case VTK_PARSE_SIGNED_CHAR:
      case VTK_PARSE_UNSIGNED_CHAR:
        fprintf(fp, "byte[] id%i", i);
        return;
    }
  }

  /* scalar types */
  switch ((aType & VTK_PARSE_BASE_TYPE) & ~VTK_PARSE_UNSIGNED)
  {
    case VTK_PARSE_FLOAT:
      fprintf(fp, "float id%i", i);
      break;
    case VTK_PARSE_DOUBLE:
      fprintf(fp, "double id%i", i);
      break;
    case VTK_PARSE_INT:
      fprintf(fp, "int id%i", i);
      break;
    case VTK_PARSE_SHORT:
      fprintf(fp, "short id%i", i);
      break;
    case VTK_PARSE_LONG:
    case VTK_PARSE_LONG_LONG:
      fprintf(fp, "long id%i", i);
      break;
    case VTK_PARSE_BOOL:
      fprintf(fp, "bool id%i", i);
      break;
    case VTK_PARSE_CHAR:
      fprintf(fp, "char id%i", i);
      break;
    case VTK_PARSE_SIGNED_CHAR:
    case VTK_PARSE_UNSIGNED_CHAR:
      fprintf(fp, "byte id%i", i);
      break;
    case VTK_PARSE_UNKNOWN: /* enum */
      fprintf(fp, "int id%i", i);
      break;
    default:
      fprintf(fp, "int id%i", i);
      break;
  }
}

/* Output C# parameter type for [DllImport] extern declarations */
static void OutputCSharpNativeParamType(FILE* fp, int i)
{
  unsigned int aType = (thisFunction->ArgTypes[i] & VTK_PARSE_UNQUALIFIED_TYPE);

  if (aType == VTK_PARSE_VOID)
  {
    return;
  }

  if (thisFunction->ArgTypes[i] == VTK_PARSE_FUNCTION)
  {
    fprintf(fp, "IntPtr fptr, IntPtr clientdata");
    return;
  }

  /* strings: marshal as UTF-8 */
  if (aType == VTK_PARSE_CHAR_PTR || aType == VTK_PARSE_STRING || aType == VTK_PARSE_STRING_REF)
  {
    fprintf(fp, "[MarshalAs(UnmanagedType.LPUTF8Str)] string id%i", i);
    return;
  }

  /* object pointer -> IntPtr */
  if (aType == VTK_PARSE_OBJECT_PTR)
  {
    fprintf(fp, "IntPtr id%i", i);
    return;
  }

  /* array types: pinned arrays via IntPtr */
  if ((aType & VTK_PARSE_INDIRECT) == VTK_PARSE_POINTER && aType != VTK_PARSE_CHAR_PTR &&
    aType != VTK_PARSE_OBJECT_PTR)
  {
    switch ((aType & VTK_PARSE_BASE_TYPE) & ~VTK_PARSE_UNSIGNED)
    {
      case VTK_PARSE_FLOAT:
        fprintf(fp, "float[] id%i", i);
        return;
      case VTK_PARSE_DOUBLE:
        fprintf(fp, "double[] id%i", i);
        return;
      case VTK_PARSE_INT:
        fprintf(fp, "int[] id%i", i);
        return;
      case VTK_PARSE_SHORT:
        fprintf(fp, "short[] id%i", i);
        return;
      case VTK_PARSE_LONG:
      case VTK_PARSE_LONG_LONG:
        fprintf(fp, "long[] id%i", i);
        return;
      case VTK_PARSE_BOOL:
        fprintf(fp, "[MarshalAs(UnmanagedType.LPArray, ArraySubType = UnmanagedType.I4)] int[] id%i",
          i);
        return;
      case VTK_PARSE_CHAR:
      case VTK_PARSE_SIGNED_CHAR:
      case VTK_PARSE_UNSIGNED_CHAR:
        fprintf(fp, "byte[] id%i", i);
        return;
    }
  }

  /* scalar types */
  switch ((aType & VTK_PARSE_BASE_TYPE) & ~VTK_PARSE_UNSIGNED)
  {
    case VTK_PARSE_FLOAT:
      fprintf(fp, "float id%i", i);
      break;
    case VTK_PARSE_DOUBLE:
      fprintf(fp, "double id%i", i);
      break;
    case VTK_PARSE_INT:
      fprintf(fp, "int id%i", i);
      break;
    case VTK_PARSE_SHORT:
      fprintf(fp, "short id%i", i);
      break;
    case VTK_PARSE_LONG:
    case VTK_PARSE_LONG_LONG:
      fprintf(fp, "long id%i", i);
      break;
    case VTK_PARSE_BOOL:
      fprintf(fp, "int id%i", i); /* bool as int for ABI safety */
      break;
    case VTK_PARSE_CHAR:
      fprintf(fp, "byte id%i", i);
      break;
    case VTK_PARSE_SIGNED_CHAR:
    case VTK_PARSE_UNSIGNED_CHAR:
      fprintf(fp, "byte id%i", i);
      break;
    case VTK_PARSE_UNKNOWN: /* enum */
      fprintf(fp, "int id%i", i);
      break;
    default:
      fprintf(fp, "int id%i", i);
      break;
  }
}

/* Output C# return type for public methods */
static void OutputCSharpReturnType(FILE* fp)
{
  unsigned int rType = (thisFunction->ReturnType & VTK_PARSE_UNQUALIFIED_TYPE);

  switch (rType)
  {
    case VTK_PARSE_VOID:
      fprintf(fp, "void");
      break;
    case VTK_PARSE_FLOAT:
      fprintf(fp, "float");
      break;
    case VTK_PARSE_DOUBLE:
      fprintf(fp, "double");
      break;
    case VTK_PARSE_CHAR:
      fprintf(fp, "char");
      break;
    case VTK_PARSE_SIGNED_CHAR:
    case VTK_PARSE_UNSIGNED_CHAR:
      fprintf(fp, "byte");
      break;
    case VTK_PARSE_SHORT:
    case VTK_PARSE_UNSIGNED_SHORT:
      fprintf(fp, "short");
      break;
    case VTK_PARSE_INT:
    case VTK_PARSE_UNSIGNED_INT:
      fprintf(fp, "int");
      break;
    case VTK_PARSE_UNKNOWN: /* enum */
      fprintf(fp, "int");
      break;
    case VTK_PARSE_LONG:
    case VTK_PARSE_LONG_LONG:
    case VTK_PARSE_UNSIGNED_LONG:
    case VTK_PARSE_UNSIGNED_LONG_LONG:
      fprintf(fp, "long");
      break;
    case VTK_PARSE_BOOL:
      fprintf(fp, "bool");
      break;
    case VTK_PARSE_CHAR_PTR:
    case VTK_PARSE_STRING:
    case VTK_PARSE_STRING_REF:
      fprintf(fp, "string");
      break;
    case VTK_PARSE_OBJECT_PTR:
      fprintf(fp, "%s", thisFunction->ReturnClass);
      break;
    case VTK_PARSE_FLOAT_PTR:
      fprintf(fp, "float[]");
      break;
    case VTK_PARSE_DOUBLE_PTR:
      fprintf(fp, "double[]");
      break;
    case VTK_PARSE_INT_PTR:
    case VTK_PARSE_UNSIGNED_INT_PTR:
      fprintf(fp, "int[]");
      break;
    case VTK_PARSE_SHORT_PTR:
    case VTK_PARSE_UNSIGNED_SHORT_PTR:
      fprintf(fp, "short[]");
      break;
    case VTK_PARSE_LONG_PTR:
    case VTK_PARSE_LONG_LONG_PTR:
    case VTK_PARSE_UNSIGNED_LONG_PTR:
    case VTK_PARSE_UNSIGNED_LONG_LONG_PTR:
      fprintf(fp, "long[]");
      break;
    case VTK_PARSE_SIGNED_CHAR_PTR:
    case VTK_PARSE_UNSIGNED_CHAR_PTR:
      fprintf(fp, "byte[]");
      break;
    case VTK_PARSE_BOOL_PTR:
      fprintf(fp, "bool[]");
      break;
    default:
      fprintf(fp, "int");
      break;
  }
}

/* Output C# return type for [DllImport] native declarations */
static void OutputCSharpNativeReturnType(FILE* fp)
{
  unsigned int rType = (thisFunction->ReturnType & VTK_PARSE_UNQUALIFIED_TYPE);

  switch (rType)
  {
    case VTK_PARSE_VOID:
      fprintf(fp, "void");
      break;
    case VTK_PARSE_FLOAT:
      fprintf(fp, "float");
      break;
    case VTK_PARSE_DOUBLE:
      fprintf(fp, "double");
      break;
    case VTK_PARSE_CHAR:
      fprintf(fp, "byte");
      break;
    case VTK_PARSE_SIGNED_CHAR:
    case VTK_PARSE_UNSIGNED_CHAR:
      fprintf(fp, "byte");
      break;
    case VTK_PARSE_SHORT:
    case VTK_PARSE_UNSIGNED_SHORT:
      fprintf(fp, "short");
      break;
    case VTK_PARSE_INT:
    case VTK_PARSE_UNSIGNED_INT:
      fprintf(fp, "int");
      break;
    case VTK_PARSE_UNKNOWN: /* enum */
      fprintf(fp, "int");
      break;
    case VTK_PARSE_LONG:
    case VTK_PARSE_LONG_LONG:
    case VTK_PARSE_UNSIGNED_LONG:
    case VTK_PARSE_UNSIGNED_LONG_LONG:
      fprintf(fp, "long");
      break;
    case VTK_PARSE_BOOL:
      fprintf(fp, "int"); /* bool as int in native */
      break;
    case VTK_PARSE_CHAR_PTR:
    case VTK_PARSE_STRING:
    case VTK_PARSE_STRING_REF:
      fprintf(fp, "IntPtr"); /* string returned as IntPtr, then marshaled */
      break;
    case VTK_PARSE_OBJECT_PTR:
      fprintf(fp, "IntPtr");
      break;
    /* pointer return types */
    case VTK_PARSE_FLOAT_PTR:
    case VTK_PARSE_DOUBLE_PTR:
    case VTK_PARSE_INT_PTR:
    case VTK_PARSE_UNSIGNED_INT_PTR:
    case VTK_PARSE_SHORT_PTR:
    case VTK_PARSE_UNSIGNED_SHORT_PTR:
    case VTK_PARSE_LONG_PTR:
    case VTK_PARSE_LONG_LONG_PTR:
    case VTK_PARSE_UNSIGNED_LONG_PTR:
    case VTK_PARSE_UNSIGNED_LONG_LONG_PTR:
    case VTK_PARSE_SIGNED_CHAR_PTR:
    case VTK_PARSE_UNSIGNED_CHAR_PTR:
    case VTK_PARSE_BOOL_PTR:
      fprintf(fp, "IntPtr");
      break;
    default:
      fprintf(fp, "int");
      break;
  }
}

/* Check if two types map to the same C# type */
static int CheckMatch(unsigned int type1, unsigned int type2, const char* c1, const char* c2)
{
  static unsigned int byteTypes[] = { VTK_PARSE_UNSIGNED_CHAR, VTK_PARSE_SIGNED_CHAR, 0 };
  static unsigned int shortTypes[] = { VTK_PARSE_UNSIGNED_SHORT, VTK_PARSE_SHORT, 0 };
  static unsigned int intTypes[] = { VTK_PARSE_UNKNOWN, VTK_PARSE_UNSIGNED_INT, VTK_PARSE_INT, 0 };
  static unsigned int longTypes[] = { VTK_PARSE_UNSIGNED_LONG, VTK_PARSE_UNSIGNED_LONG_LONG,
    VTK_PARSE_LONG, VTK_PARSE_LONG_LONG, 0 };
  static unsigned int stringTypes[] = { VTK_PARSE_CHAR_PTR, VTK_PARSE_STRING_REF, VTK_PARSE_STRING,
    0 };
  static unsigned int* numericTypes[] = { byteTypes, shortTypes, intTypes, longTypes, 0 };

  int i, j;
  int hit1, hit2;

  if ((type1 & VTK_PARSE_UNQUALIFIED_TYPE) == (type2 & VTK_PARSE_UNQUALIFIED_TYPE))
  {
    if ((type1 & VTK_PARSE_BASE_TYPE) == VTK_PARSE_OBJECT)
    {
      return strcmp(c1, c2) == 0 ? 1 : 0;
    }
    return 1;
  }

  for (i = 0; numericTypes[i]; i++)
  {
    hit1 = 0;
    hit2 = 0;
    for (j = 0; numericTypes[i][j]; j++)
    {
      if ((type1 & VTK_PARSE_BASE_TYPE) == numericTypes[i][j])
        hit1 = j + 1;
      if ((type2 & VTK_PARSE_BASE_TYPE) == numericTypes[i][j])
        hit2 = j + 1;
    }
    if (hit1 && hit2 && (type1 & VTK_PARSE_INDIRECT) == (type2 & VTK_PARSE_INDIRECT))
    {
      return hit1 < hit2 ? 1 : 2;
    }
  }

  hit1 = 0;
  hit2 = 0;
  for (j = 0; stringTypes[j]; j++)
  {
    if ((type1 & VTK_PARSE_UNQUALIFIED_TYPE) == stringTypes[j])
      hit1 = j + 1;
    if ((type2 & VTK_PARSE_UNQUALIFIED_TYPE) == stringTypes[j])
      hit2 = j + 1;
  }
  if (hit1 && hit2)
  {
    return hit1 < hit2 ? 1 : 2;
  }

  return 0;
}

static int DoneOne(void)
{
  int i, j;
  int match;
  const FunctionInfo* fi;

  for (i = 0; i < numberOfWrappedFunctions; i++)
  {
    fi = wrappedFunctions[i];
    if ((!strcmp(fi->Name, thisFunction->Name)) &&
      (fi->NumberOfArguments == thisFunction->NumberOfArguments))
    {
      match = 1;
      for (j = 0; j < fi->NumberOfArguments; j++)
      {
        if (!CheckMatch(thisFunction->ArgTypes[j], fi->ArgTypes[j], thisFunction->ArgClasses[j],
              fi->ArgClasses[j]))
          match = 0;
      }
      if (!CheckMatch(
            thisFunction->ReturnType, fi->ReturnType, thisFunction->ReturnClass, fi->ReturnClass))
        match = 0;
      if (match)
        return 1;
    }
  }
  return 0;
}

static int isClassWrapped(const char* classname)
{
  const HierarchyEntry* entry;

  if (hierarchyInfo)
  {
    entry = vtkParseHierarchy_FindEntry(hierarchyInfo, classname);
    if (entry == 0 || vtkParseHierarchy_GetProperty(entry, "WRAPEXCLUDE") ||
      !vtkParseHierarchy_IsTypeOf(hierarchyInfo, entry, "vtkObjectBase"))
    {
      return 0;
    }
    if (strchr(classname, '<'))
    {
      return 0;
    }
    return vtkParseHierarchy_IsPrimary(entry);
  }

  return 1;
}

static int checkFunctionSignature(ClassInfo* data)
{
  static const unsigned int supported_types[] = { VTK_PARSE_VOID, VTK_PARSE_BOOL, VTK_PARSE_FLOAT,
    VTK_PARSE_DOUBLE, VTK_PARSE_CHAR, VTK_PARSE_UNSIGNED_CHAR, VTK_PARSE_SIGNED_CHAR, VTK_PARSE_INT,
    VTK_PARSE_UNSIGNED_INT, VTK_PARSE_SHORT, VTK_PARSE_UNSIGNED_SHORT, VTK_PARSE_LONG,
    VTK_PARSE_UNSIGNED_LONG, VTK_PARSE_LONG_LONG, VTK_PARSE_UNSIGNED_LONG_LONG, VTK_PARSE_OBJECT,
    VTK_PARSE_STRING, VTK_PARSE_UNKNOWN, 0 };

  int i, j;
  int args_ok = 1;
  unsigned int rType = (thisFunction->ReturnType & VTK_PARSE_UNQUALIFIED_TYPE);
  unsigned int aType = 0;
  unsigned int baseType = 0;

  if (thisFunction->IsOperator || thisFunction->ArrayFailure || thisFunction->Template ||
    thisFunction->IsExcluded || thisFunction->IsDeleted || !thisFunction->IsPublic ||
    !thisFunction->Name)
  {
    return 0;
  }

  if (!strcmp("NewInstance", thisFunction->Name))
    return 0;
  if (!strcmp("SafeDownCast", thisFunction->Name))
    return 0;

  /* function pointer arguments for callbacks */
  if (thisFunction->NumberOfArguments == 2 && thisFunction->ArgTypes[0] == VTK_PARSE_FUNCTION &&
    thisFunction->ArgTypes[1] == VTK_PARSE_VOID_PTR && rType == VTK_PARSE_VOID)
  {
    return 1;
  }

  for (i = 0; i < thisFunction->NumberOfArguments; i++)
  {
    aType = (thisFunction->ArgTypes[i] & VTK_PARSE_UNQUALIFIED_TYPE);
    baseType = (aType & VTK_PARSE_BASE_TYPE);

    for (j = 0; supported_types[j] != 0; j++)
    {
      if (baseType == supported_types[j])
        break;
    }
    if (supported_types[j] == 0)
      args_ok = 0;

    if (baseType == VTK_PARSE_UNKNOWN)
    {
      const char* qualified_name = 0;
      if ((aType & VTK_PARSE_INDIRECT) == 0)
      {
        qualified_name = vtkParseHierarchy_QualifiedEnumName(
          hierarchyInfo, data, stringCache, thisFunction->ArgClasses[i]);
      }
      if (qualified_name)
        thisFunction->ArgClasses[i] = qualified_name;
      else
        args_ok = 0;
    }

    if (baseType == VTK_PARSE_OBJECT)
    {
      if ((aType & VTK_PARSE_INDIRECT) != VTK_PARSE_POINTER)
        args_ok = 0;
      else if (!isClassWrapped(thisFunction->ArgClasses[i]))
        args_ok = 0;
    }

    if (aType == VTK_PARSE_OBJECT)
      args_ok = 0;
    if (((aType & VTK_PARSE_INDIRECT) != VTK_PARSE_POINTER) &&
      ((aType & VTK_PARSE_INDIRECT) != 0) && (aType != VTK_PARSE_STRING_REF))
      args_ok = 0;
    if (aType == VTK_PARSE_STRING_PTR)
      args_ok = 0;
    if (aType == VTK_PARSE_UNSIGNED_CHAR_PTR)
      args_ok = 0;
    if (aType == VTK_PARSE_UNSIGNED_INT_PTR)
      args_ok = 0;
    if (aType == VTK_PARSE_UNSIGNED_SHORT_PTR)
      args_ok = 0;
    if (aType == VTK_PARSE_UNSIGNED_LONG_PTR)
      args_ok = 0;
    if (aType == VTK_PARSE_UNSIGNED_LONG_LONG_PTR)
      args_ok = 0;
  }

  baseType = (rType & VTK_PARSE_BASE_TYPE);
  for (j = 0; supported_types[j] != 0; j++)
  {
    if (baseType == supported_types[j])
      break;
  }
  if (supported_types[j] == 0)
    args_ok = 0;

  if (baseType == VTK_PARSE_UNKNOWN)
  {
    const char* qualified_name = 0;
    if ((rType & VTK_PARSE_INDIRECT) == 0)
    {
      qualified_name = vtkParseHierarchy_QualifiedEnumName(
        hierarchyInfo, data, stringCache, thisFunction->ReturnClass);
    }
    if (qualified_name)
      thisFunction->ReturnClass = qualified_name;
    else
      args_ok = 0;
  }

  if (baseType == VTK_PARSE_OBJECT)
  {
    if ((rType & VTK_PARSE_INDIRECT) != VTK_PARSE_POINTER)
      args_ok = 0;
    else if (!isClassWrapped(thisFunction->ReturnClass))
      args_ok = 0;
  }

  if (((rType & VTK_PARSE_INDIRECT) != VTK_PARSE_POINTER) && ((rType & VTK_PARSE_INDIRECT) != 0) &&
    (rType != VTK_PARSE_STRING_REF))
    args_ok = 0;
  if (rType == VTK_PARSE_STRING_PTR)
    args_ok = 0;
  if (rType == VTK_PARSE_UNSIGNED_CHAR_PTR)
    args_ok = 0;
  if (rType == VTK_PARSE_UNSIGNED_INT_PTR)
    args_ok = 0;
  if (rType == VTK_PARSE_UNSIGNED_SHORT_PTR)
    args_ok = 0;
  if (rType == VTK_PARSE_UNSIGNED_LONG_PTR)
    args_ok = 0;
  if (rType == VTK_PARSE_UNSIGNED_LONG_LONG_PTR)
    args_ok = 0;

  for (i = 0; i < thisFunction->NumberOfArguments; i++)
  {
    aType = (thisFunction->ArgTypes[i] & VTK_PARSE_UNQUALIFIED_TYPE);
    if (((aType & VTK_PARSE_INDIRECT) == VTK_PARSE_POINTER) && (thisFunction->ArgCounts[i] <= 0) &&
      (aType != VTK_PARSE_OBJECT_PTR) && (aType != VTK_PARSE_CHAR_PTR))
      args_ok = 0;
  }

  switch (rType)
  {
    case VTK_PARSE_FLOAT_PTR:
    case VTK_PARSE_VOID_PTR:
    case VTK_PARSE_DOUBLE_PTR:
    case VTK_PARSE_INT_PTR:
    case VTK_PARSE_SHORT_PTR:
    case VTK_PARSE_LONG_PTR:
    case VTK_PARSE_LONG_LONG_PTR:
    case VTK_PARSE_SIGNED_CHAR_PTR:
    case VTK_PARSE_BOOL_PTR:
    case VTK_PARSE_UNSIGNED_CHAR_PTR:
      args_ok = thisFunction->HaveHint;
      break;
  }

  if (!strcmp("vtkObject", data->Name))
  {
    if (!strcmp(thisFunction->Name, "AddObserver") || !strcmp(thisFunction->Name, "GetCommand") ||
      (!strcmp(thisFunction->Name, "RemoveObserver") &&
        (thisFunction->ArgTypes[0] != VTK_PARSE_UNSIGNED_LONG)) ||
      ((!strcmp(thisFunction->Name, "RemoveObservers") ||
         !strcmp(thisFunction->Name, "HasObserver")) &&
        (((thisFunction->ArgTypes[0] != VTK_PARSE_UNSIGNED_LONG) &&
           (thisFunction->ArgTypes[0] != (VTK_PARSE_CHAR_PTR | VTK_PARSE_CONST))) ||
          (thisFunction->NumberOfArguments > 1))) ||
      (!strcmp(thisFunction->Name, "RemoveAllObservers") && (thisFunction->NumberOfArguments > 0)))
    {
      args_ok = 0;
    }
  }
  else if (!strcmp("vtkObjectBase", data->Name))
  {
    if (!strcmp(thisFunction->Name, "Print"))
      args_ok = 0;
  }

  if (!strcmp("Delete", thisFunction->Name) || !strcmp("New", thisFunction->Name))
    args_ok = 0;

  return args_ok;
}

/* Output the call arguments for the public wrapper calling the native method */
static void OutputCallArgs(FILE* fp)
{
  int i;
  unsigned int aType;

  fprintf(fp, "Handle");

  for (i = 0; i < thisFunction->NumberOfArguments; i++)
  {
    aType = (thisFunction->ArgTypes[i] & VTK_PARSE_UNQUALIFIED_TYPE);

    if (thisFunction->ArgTypes[i] == VTK_PARSE_FUNCTION)
    {
      fprintf(
        fp, ", Marshal.GetFunctionPointerForDelegate(id0), IntPtr.Zero");
      break;
    }

    fprintf(fp, ", ");

    if (aType == VTK_PARSE_OBJECT_PTR)
    {
      fprintf(fp, "id%i == null ? IntPtr.Zero : id%i.Handle", i, i);
    }
    else if (aType == VTK_PARSE_BOOL)
    {
      fprintf(fp, "id%i ? 1 : 0", i);
    }
    else
    {
      fprintf(fp, "id%i", i);
    }
  }
}

static void outputFunction(FILE* fp, ClassInfo* data)
{
  unsigned int rType = (thisFunction->ReturnType & VTK_PARSE_UNQUALIFIED_TYPE);
  int i;
  int args_ok = checkFunctionSignature(data);

  if (!thisFunction->IsExcluded && thisFunction->IsPublic && args_ok &&
    strcmp(data->Name, thisFunction->Name) != 0 && strcmp(data->Name, thisFunction->Name + 1) != 0)
  {
    if (!DoneOne())
    {
      /* DllImport declaration */
      fprintf(fp, "\n    [DllImport(NativeLib, CallingConvention = CallingConvention.Cdecl)]\n");
      fprintf(fp, "    private static extern ");
      OutputCSharpNativeReturnType(fp);
      fprintf(fp, " %s_%s_%i(IntPtr obj", data->Name, thisFunction->Name,
        numberOfWrappedFunctions);

      for (i = 0; i < thisFunction->NumberOfArguments; i++)
      {
        fprintf(fp, ", ");
        OutputCSharpNativeParamType(fp, i);
        if (thisFunction->ArgTypes[i] == VTK_PARSE_FUNCTION)
          break;
      }
      fprintf(fp, ");\n");

      /* Public wrapper method */
      fprintf(fp, "    public ");
      OutputCSharpReturnType(fp);
      fprintf(fp, " %s(", thisFunction->Name);
      for (i = 0; i < thisFunction->NumberOfArguments; i++)
      {
        if (i)
          fprintf(fp, ", ");
        OutputCSharpParamType(fp, i);
        if (thisFunction->ArgTypes[i] == VTK_PARSE_FUNCTION)
          break;
      }
      fprintf(fp, ")\n    {\n");

      /* method body */
      if (rType == VTK_PARSE_OBJECT_PTR)
      {
        fprintf(fp, "        IntPtr temp = %s_%s_%i(", data->Name, thisFunction->Name,
          numberOfWrappedFunctions);
        OutputCallArgs(fp);
        fprintf(fp, ");\n");
        fprintf(fp, "        if (temp == IntPtr.Zero) return null;\n");
        fprintf(
          fp, "        return (%s)vtkObjectBase.OBJECT_MANAGER.GetOrCreate(temp, typeof(%s));\n",
          thisFunction->ReturnClass, thisFunction->ReturnClass);
      }
      else if (rType == VTK_PARSE_CHAR_PTR || rType == VTK_PARSE_STRING ||
        rType == VTK_PARSE_STRING_REF)
      {
        fprintf(fp, "        IntPtr temp = %s_%s_%i(", data->Name, thisFunction->Name,
          numberOfWrappedFunctions);
        OutputCallArgs(fp);
        fprintf(fp, ");\n");
        fprintf(fp,
          "        return temp == IntPtr.Zero ? null : Marshal.PtrToStringUTF8(temp);\n");
      }
      else if (rType == VTK_PARSE_BOOL)
      {
        fprintf(fp, "        return %s_%s_%i(", data->Name, thisFunction->Name,
          numberOfWrappedFunctions);
        OutputCallArgs(fp);
        fprintf(fp, ") != 0;\n");
      }
      else if (rType == VTK_PARSE_FLOAT_PTR || rType == VTK_PARSE_DOUBLE_PTR ||
        rType == VTK_PARSE_INT_PTR || rType == VTK_PARSE_UNSIGNED_INT_PTR ||
        rType == VTK_PARSE_SHORT_PTR || rType == VTK_PARSE_UNSIGNED_SHORT_PTR ||
        rType == VTK_PARSE_LONG_PTR || rType == VTK_PARSE_LONG_LONG_PTR ||
        rType == VTK_PARSE_UNSIGNED_LONG_PTR || rType == VTK_PARSE_UNSIGNED_LONG_LONG_PTR ||
        rType == VTK_PARSE_SIGNED_CHAR_PTR || rType == VTK_PARSE_UNSIGNED_CHAR_PTR ||
        rType == VTK_PARSE_BOOL_PTR)
      {
        int count = thisFunction->ReturnValue->Count;
        fprintf(fp, "        IntPtr temp = %s_%s_%i(", data->Name, thisFunction->Name,
          numberOfWrappedFunctions);
        OutputCallArgs(fp);
        fprintf(fp, ");\n");

        /* determine the element type for Marshal.Copy */
        switch (rType)
        {
          case VTK_PARSE_FLOAT_PTR:
            fprintf(fp, "        float[] result = new float[%i];\n", count);
            fprintf(fp, "        Marshal.Copy(temp, result, 0, %i);\n", count);
            break;
          case VTK_PARSE_DOUBLE_PTR:
            fprintf(fp, "        double[] result = new double[%i];\n", count);
            fprintf(fp, "        Marshal.Copy(temp, result, 0, %i);\n", count);
            break;
          case VTK_PARSE_INT_PTR:
          case VTK_PARSE_UNSIGNED_INT_PTR:
            fprintf(fp, "        int[] result = new int[%i];\n", count);
            fprintf(fp, "        Marshal.Copy(temp, result, 0, %i);\n", count);
            break;
          case VTK_PARSE_SHORT_PTR:
          case VTK_PARSE_UNSIGNED_SHORT_PTR:
            fprintf(fp, "        short[] result = new short[%i];\n", count);
            fprintf(fp, "        Marshal.Copy(temp, result, 0, %i);\n", count);
            break;
          case VTK_PARSE_LONG_PTR:
          case VTK_PARSE_LONG_LONG_PTR:
          case VTK_PARSE_UNSIGNED_LONG_PTR:
          case VTK_PARSE_UNSIGNED_LONG_LONG_PTR:
            fprintf(fp, "        long[] result = new long[%i];\n", count);
            fprintf(fp, "        Marshal.Copy(temp, result, 0, %i);\n", count);
            break;
          case VTK_PARSE_SIGNED_CHAR_PTR:
          case VTK_PARSE_UNSIGNED_CHAR_PTR:
            fprintf(fp, "        byte[] result = new byte[%i];\n", count);
            fprintf(fp, "        Marshal.Copy(temp, result, 0, %i);\n", count);
            break;
          case VTK_PARSE_BOOL_PTR:
            fprintf(fp, "        int[] raw = new int[%i];\n", count);
            fprintf(fp, "        Marshal.Copy(temp, raw, 0, %i);\n", count);
            fprintf(fp, "        bool[] result = new bool[%i];\n", count);
            fprintf(fp, "        for (int _i = 0; _i < %i; _i++) result[_i] = raw[_i] != 0;\n",
              count);
            break;
        }
        fprintf(fp, "        return result;\n");
      }
      else if (rType == VTK_PARSE_VOID)
      {
        fprintf(fp, "        %s_%s_%i(", data->Name, thisFunction->Name,
          numberOfWrappedFunctions);
        OutputCallArgs(fp);
        fprintf(fp, ");\n");
      }
      else
      {
        /* scalar return */
        fprintf(fp, "        return %s_%s_%i(", data->Name, thisFunction->Name,
          numberOfWrappedFunctions);
        OutputCallArgs(fp);
        fprintf(fp, ");\n");
      }

      fprintf(fp, "    }\n");

      wrappedFunctions[numberOfWrappedFunctions] = thisFunction;
      numberOfWrappedFunctions++;
    }
  }
}

/* Parse --native-lib argument from argv, remove it, return remaining argc */
static int ParseNativeLib(int argc, char* argv[])
{
  int i, j;
  for (i = 1; i < argc - 1; i++)
  {
    if (strcmp(argv[i], "--native-lib") == 0)
    {
      nativeLibName = argv[i + 1];
      /* remove these two arguments */
      for (j = i; j < argc - 2; j++)
      {
        argv[j] = argv[j + 2];
      }
      return argc - 2;
    }
  }
  return argc;
}

int VTK_PARSE_MAIN(int argc, char* argv[])
{
  const OptionInfo* options;
  FileInfo* file_info;
  ClassInfo* data;
  FILE* fp;
  int i;

  /* parse custom argument before vtkParse_Main */
  argc = ParseNativeLib(argc, argv);

  /* pre-define a macro to identify the language */
  vtkParse_DefineMacro("__VTK_WRAP_CSHARP__", 0);

  /* get command-line args and parse the header file */
  file_info = vtkParse_Main(argc, argv);

  stringCache = file_info->Strings;

  options = vtkParse_GetCommandLineOptions();

  if (options->HierarchyFileNames)
  {
    hierarchyInfo =
      vtkParseHierarchy_ReadFiles(options->NumberOfHierarchyFileNames, options->HierarchyFileNames);
  }

  fp = vtkParse_FileOpen(options->OutputFileName, "w");
  if (!fp)
  {
    fprintf(stderr, "Error opening output file %s\n", options->OutputFileName);
    return vtkParse_FinalizeMain(1);
  }

  data = file_info->MainClass;
  if (data == NULL || data->IsExcluded)
  {
    /* write empty stub class */
    fprintf(fp, "namespace VTK { }\n");
    fclose(fp);
    vtkWrap_WarnEmpty(options);
    return vtkParse_FinalizeMain(0);
  }

  /* Skip vtkObjectBase — use the hand-written managed base class instead */
  if (strcmp(data->Name, "vtkObjectBase") == 0)
  {
    fprintf(fp, "namespace VTK { }\n");
    fclose(fp);
    return vtkParse_FinalizeMain(0);
  }

  if (data->Template)
  {
    fprintf(fp, "namespace VTK { }\n");
    fclose(fp);
    vtkWrap_WarnEmpty(options);
    return vtkParse_FinalizeMain(0);
  }

  for (i = 0; i < data->NumberOfSuperClasses; ++i)
  {
    if (strchr(data->SuperClasses[i], '<'))
    {
      fprintf(fp, "namespace VTK { }\n");
      fclose(fp);
      vtkWrap_WarnEmpty(options);
      return vtkParse_FinalizeMain(0);
    }
  }

  if (hierarchyInfo)
  {
    if (!vtkWrap_IsTypeOf(hierarchyInfo, data->Name, "vtkObjectBase"))
    {
      fprintf(fp, "namespace VTK { }\n");
      fclose(fp);
      vtkWrap_WarnEmpty(options);
      return vtkParse_FinalizeMain(0);
    }

    vtkWrap_ApplyUsingDeclarations(data, file_info, hierarchyInfo);
    vtkWrap_ExpandTypedefs(data, file_info, hierarchyInfo);
  }

  /* file header */
  fprintf(fp, "// C# wrapper for %s object\n", data->Name);
  fprintf(fp, "// Auto-generated by vtkParseCSharp - do not edit\n\n");
  fprintf(fp, "using System;\n");
  fprintf(fp, "using System.Runtime.InteropServices;\n\n");
  fprintf(fp, "namespace VTK\n{\n");

  /* class declaration */
  fprintf(fp, "    public class %s", data->Name);
  if (data->NumberOfSuperClasses > 0)
  {
    fprintf(fp, " : %s", data->SuperClasses[0]);
  }
  else if (strcmp("vtkObjectBase", data->Name) != 0)
  {
    fprintf(fp, " : vtkObjectBase");
  }
  fprintf(fp, "\n    {\n");

  /* native library name constant */
  fprintf(fp, "        private const string NativeLib = \"%s\";\n\n", nativeLibName);

  /* methods */
  for (i = 0; i < data->NumberOfFunctions; i++)
  {
    thisFunction = data->Functions[i];
    outputFunction(fp, data);
  }

  /* base class (vtkObjectBase) infrastructure */
  if (!data->NumberOfSuperClasses)
  {
    if (strcmp("vtkObjectBase", data->Name) == 0)
    {
      fprintf(fp, "\n        // Object manager for identity mapping\n");
      fprintf(fp, "        public static VtkObjectManager OBJECT_MANAGER = new VtkObjectManager();\n");
    }

    fprintf(fp, "\n        protected IntPtr handle;\n");
    fprintf(fp, "        private bool ownsReference;\n");
    fprintf(fp, "        private bool disposed;\n\n");

    fprintf(fp, "        public IntPtr Handle\n");
    fprintf(fp, "        {\n");
    fprintf(fp, "            get\n");
    fprintf(fp, "            {\n");
    fprintf(fp, "                if (disposed) throw new ObjectDisposedException(GetType().Name);\n");
    fprintf(fp, "                return handle;\n");
    fprintf(fp, "            }\n");
    fprintf(fp, "        }\n\n");

    if (!data->IsAbstract)
    {
      fprintf(fp, "        [DllImport(NativeLib, CallingConvention = CallingConvention.Cdecl)]\n");
      fprintf(fp, "        private static extern IntPtr %s_New();\n\n", data->Name);
      fprintf(fp, "        public %s()\n", data->Name);
      fprintf(fp, "        {\n");
      fprintf(fp, "            this.handle = %s_New();\n", data->Name);
      fprintf(fp, "            this.ownsReference = true;\n");
      fprintf(fp, "            OBJECT_MANAGER.Register(this.handle, this);\n");
      fprintf(fp, "        }\n\n");
    }
    else
    {
      fprintf(fp, "        protected %s() { }\n\n", data->Name);
    }

    fprintf(fp, "        internal %s(IntPtr ptr, bool ownsRef)\n", data->Name);
    fprintf(fp, "        {\n");
    fprintf(fp, "            this.handle = ptr;\n");
    fprintf(fp, "            this.ownsReference = ownsRef;\n");
    fprintf(fp, "            if (ptr != IntPtr.Zero)\n");
    fprintf(fp, "                OBJECT_MANAGER.Register(ptr, this);\n");
    fprintf(fp, "        }\n\n");

    /* lifecycle */
    if (data->HasDelete)
    {
      fprintf(fp, "        [DllImport(NativeLib, CallingConvention = CallingConvention.Cdecl)]\n");
      fprintf(
        fp, "        private static extern void %s_VTKDeleteReference(IntPtr id);\n\n", data->Name);

      fprintf(fp, "        [DllImport(NativeLib, CallingConvention = CallingConvention.Cdecl)]\n");
      fprintf(fp, "        private static extern void %s_VTKRegister(IntPtr obj);\n\n", data->Name);

      fprintf(fp, "        [DllImport(NativeLib, CallingConvention = CallingConvention.Cdecl)]\n");
      fprintf(
        fp, "        private static extern IntPtr %s_VTKGetClassName(IntPtr id);\n\n", data->Name);

      fprintf(fp, "        public static void VTKDeleteReference(IntPtr id)\n");
      fprintf(fp, "        {\n");
      fprintf(fp, "            %s_VTKDeleteReference(id);\n", data->Name);
      fprintf(fp, "        }\n\n");

      fprintf(fp, "        public static void VTKRegister(IntPtr obj)\n");
      fprintf(fp, "        {\n");
      fprintf(fp, "            %s_VTKRegister(obj);\n", data->Name);
      fprintf(fp, "        }\n\n");

      fprintf(fp, "        public static string VTKGetClassNameFromHandle(IntPtr id)\n");
      fprintf(fp, "        {\n");
      fprintf(fp, "            IntPtr ptr = %s_VTKGetClassName(id);\n", data->Name);
      fprintf(fp, "            return Marshal.PtrToStringUTF8(ptr);\n");
      fprintf(fp, "        }\n\n");

      fprintf(fp, "        public void Dispose()\n");
      fprintf(fp, "        {\n");
      fprintf(fp, "            if (!disposed && handle != IntPtr.Zero)\n");
      fprintf(fp, "            {\n");
      fprintf(fp, "                OBJECT_MANAGER.Unregister(handle);\n");
      fprintf(fp, "                if (ownsReference)\n");
      fprintf(fp, "                    %s_VTKDeleteReference(handle);\n", data->Name);
      fprintf(fp, "                handle = IntPtr.Zero;\n");
      fprintf(fp, "                disposed = true;\n");
      fprintf(fp, "            }\n");
      fprintf(fp, "            GC.SuppressFinalize(this);\n");
      fprintf(fp, "        }\n\n");

      fprintf(fp, "        ~%s() { Dispose(); }\n", data->Name);
    }
  }
  else
  {
    /* derived class constructors */
    if (!data->IsAbstract)
    {
      fprintf(fp, "\n        [DllImport(NativeLib, CallingConvention = CallingConvention.Cdecl)]\n");
      fprintf(fp, "        private static extern IntPtr %s_New();\n\n", data->Name);
      fprintf(fp, "        public %s() : base(%s_New(), true) { }\n", data->Name, data->Name);
    }
    else
    {
      fprintf(fp, "\n        protected %s() : base() { }\n", data->Name);
    }
    fprintf(fp, "        internal %s(IntPtr ptr, bool ownsRef) : base(ptr, ownsRef) { }\n",
      data->Name);
  }

  /* vtkObjectBase: Print method */
  if (!strcmp("vtkObjectBase", data->Name))
  {
    fprintf(fp, "\n        [DllImport(NativeLib, CallingConvention = CallingConvention.Cdecl)]\n");
    fprintf(fp, "        private static extern IntPtr vtkObjectBase_Print(IntPtr obj);\n\n");
    fprintf(fp, "        public string Print()\n");
    fprintf(fp, "        {\n");
    fprintf(fp, "            IntPtr ptr = vtkObjectBase_Print(Handle);\n");
    fprintf(fp, "            return Marshal.PtrToStringUTF8(ptr);\n");
    fprintf(fp, "        }\n\n");
    fprintf(fp, "        public override string ToString() => Print();\n");
  }

  /* vtkObject: AddObserver */
  if (!strcmp("vtkObject", data->Name))
  {
    fprintf(fp,
      "\n        [DllImport(NativeLib, CallingConvention = CallingConvention.Cdecl)]\n");
    fprintf(fp,
      "        private static extern ulong vtkObject_AddObserverCSharp(\n");
    fprintf(fp,
      "            IntPtr obj, [MarshalAs(UnmanagedType.LPUTF8Str)] string eventName,\n");
    fprintf(fp, "            IntPtr callbackPtr);\n\n");

    fprintf(fp,
      "        [DllImport(NativeLib, CallingConvention = CallingConvention.Cdecl)]\n");
    fprintf(fp,
      "        private static extern void vtkObject_RemoveObserverCSharp(IntPtr obj, ulong tag);\n\n");

    fprintf(fp, "        public delegate void VtkEventCallback();\n\n");

    fprintf(fp, "        public ulong AddObserver(string eventName, VtkEventCallback callback)\n");
    fprintf(fp, "        {\n");
    fprintf(fp, "            IntPtr fptr = Marshal.GetFunctionPointerForDelegate(callback);\n");
    fprintf(fp, "            return vtkObject_AddObserverCSharp(Handle, eventName, fptr);\n");
    fprintf(fp, "        }\n\n");

    fprintf(fp, "        public void RemoveObserver(ulong tag)\n");
    fprintf(fp, "        {\n");
    fprintf(fp, "            vtkObject_RemoveObserverCSharp(Handle, tag);\n");
    fprintf(fp, "        }\n");
  }

  /* close class and namespace */
  fprintf(fp, "    }\n");
  fprintf(fp, "}\n");

  fclose(fp);

  if (hierarchyInfo)
  {
    vtkParseHierarchy_Free(hierarchyInfo);
  }

  vtkParse_Free(file_info);

  return vtkParse_FinalizeMain(0);
}

// NOLINTEND(bugprone-unsafe-functions)
