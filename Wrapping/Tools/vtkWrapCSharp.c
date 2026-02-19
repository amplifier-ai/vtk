// SPDX-FileCopyrightText: Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
// SPDX-License-Identifier: BSD-3-Clause

// C# P/Invoke wrapper generator for VTK
// Generates extern "C" export functions that can be called from C# via [DllImport]
// Modeled on vtkWrapJava.c

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
static ClassInfo* thisClass;

/* Platform export macro */
static void OutputExportMacro(FILE* fp)
{
  fprintf(fp, "#ifdef _WIN32\n");
  fprintf(fp, "#define VTK_CSHARP_EXPORT __declspec(dllexport)\n");
  fprintf(fp, "#else\n");
  fprintf(fp, "#define VTK_CSHARP_EXPORT __attribute__((visibility(\"default\")))\n");
  fprintf(fp, "#endif\n\n");
}

/* Output the C parameter type for extern "C" function signatures */
static void OutputParamType(FILE* fp, int i)
{
  unsigned int aType = (thisFunction->ArgTypes[i] & VTK_PARSE_UNQUALIFIED_TYPE);

  /* ignore void */
  if (aType == VTK_PARSE_VOID)
  {
    return;
  }

  /* function pointer callback */
  if (thisFunction->ArgTypes[i] == VTK_PARSE_FUNCTION)
  {
    fprintf(fp, "void* fptr, void* clientdata");
    return;
  }

  /* strings: pass as const char* (P/Invoke marshals automatically) */
  if (((thisFunction->Parameters[i]->CountHint == NULL) && (aType == VTK_PARSE_CHAR_PTR)) ||
    (aType == VTK_PARSE_STRING) || (aType == VTK_PARSE_STRING_REF))
  {
    fprintf(fp, "const char* id%i", i);
    return;
  }

  /* array pointer types */
  if (aType == VTK_PARSE_BOOL_PTR)
  {
    fprintf(fp, "int* id%i", i);
    return;
  }
  if (aType == VTK_PARSE_FLOAT_PTR)
  {
    fprintf(fp, "float* id%i", i);
    return;
  }
  if (aType == VTK_PARSE_DOUBLE_PTR)
  {
    fprintf(fp, "double* id%i", i);
    return;
  }
  if (((thisFunction->Parameters[i]->CountHint != NULL) && (aType == VTK_PARSE_CHAR_PTR)) ||
    (aType == VTK_PARSE_SIGNED_CHAR_PTR) || (aType == VTK_PARSE_UNSIGNED_CHAR_PTR))
  {
    fprintf(fp, "unsigned char* id%i", i);
    return;
  }
  if (aType == VTK_PARSE_SHORT_PTR || aType == VTK_PARSE_UNSIGNED_SHORT_PTR)
  {
    fprintf(fp, "short* id%i", i);
    return;
  }
  if (aType == VTK_PARSE_INT_PTR || aType == VTK_PARSE_UNSIGNED_INT_PTR)
  {
    fprintf(fp, "int* id%i", i);
    return;
  }
  if ((aType == VTK_PARSE_LONG_PTR) || (aType == VTK_PARSE_LONG_LONG_PTR) ||
    (aType == VTK_PARSE_UNSIGNED_LONG_PTR) || (aType == VTK_PARSE_UNSIGNED_LONG_LONG_PTR))
  {
    fprintf(fp, "long long* id%i", i);
    return;
  }

  /* object pointer */
  switch ((aType & VTK_PARSE_BASE_TYPE) & ~VTK_PARSE_UNSIGNED)
  {
    case VTK_PARSE_FLOAT:
      fprintf(fp, "float id%i", i);
      break;
    case VTK_PARSE_DOUBLE:
      fprintf(fp, "double id%i", i);
      break;
    case VTK_PARSE_SHORT:
      fprintf(fp, "short id%i", i);
      break;
    case VTK_PARSE_INT:
      fprintf(fp, "int id%i", i);
      break;
    case VTK_PARSE_LONG:
    case VTK_PARSE_LONG_LONG:
      fprintf(fp, "long long id%i", i);
      break;
    case VTK_PARSE_BOOL:
      fprintf(fp, "int id%i", i);
      break;
    case VTK_PARSE_CHAR:
      fprintf(fp, "char id%i", i);
      break;
    case VTK_PARSE_SIGNED_CHAR:
      fprintf(fp, "signed char id%i", i);
      break;
    case VTK_PARSE_UNSIGNED_CHAR:
      fprintf(fp, "unsigned char id%i", i);
      break;
    case VTK_PARSE_OBJECT:
      fprintf(fp, "void* id%i", i);
      break;
    case VTK_PARSE_UNKNOWN: /* enum */
      fprintf(fp, "int id%i", i);
      break;
    default:
      fprintf(fp, "int id%i", i);
      break;
  }
}

/* Output the C return type for extern "C" functions */
static void OutputReturnType(FILE* fp)
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
      fprintf(fp, "unsigned char");
      break;
    case VTK_PARSE_SHORT:
    case VTK_PARSE_UNSIGNED_SHORT:
      fprintf(fp, "short");
      break;
    case VTK_PARSE_INT:
    case VTK_PARSE_UNSIGNED_INT:
      fprintf(fp, "int");
      break;
    case VTK_PARSE_LONG:
    case VTK_PARSE_LONG_LONG:
    case VTK_PARSE_UNSIGNED_LONG:
    case VTK_PARSE_UNSIGNED_LONG_LONG:
      fprintf(fp, "long long");
      break;
    case VTK_PARSE_BOOL:
      fprintf(fp, "int");
      break;
    case VTK_PARSE_UNKNOWN: /* enum */
      fprintf(fp, "int");
      break;
    case VTK_PARSE_OBJECT_PTR:
      fprintf(fp, "void*");
      break;
    case VTK_PARSE_CHAR_PTR:
    case VTK_PARSE_STRING:
    case VTK_PARSE_STRING_REF:
      fprintf(fp, "const char*");
      break;
    /* pointer return types */
    case VTK_PARSE_FLOAT_PTR:
      fprintf(fp, "float*");
      break;
    case VTK_PARSE_DOUBLE_PTR:
      fprintf(fp, "double*");
      break;
    case VTK_PARSE_INT_PTR:
    case VTK_PARSE_UNSIGNED_INT_PTR:
      fprintf(fp, "int*");
      break;
    case VTK_PARSE_SHORT_PTR:
    case VTK_PARSE_UNSIGNED_SHORT_PTR:
      fprintf(fp, "short*");
      break;
    case VTK_PARSE_LONG_PTR:
    case VTK_PARSE_LONG_LONG_PTR:
    case VTK_PARSE_UNSIGNED_LONG_PTR:
    case VTK_PARSE_UNSIGNED_LONG_LONG_PTR:
      fprintf(fp, "long long*");
      break;
    case VTK_PARSE_SIGNED_CHAR_PTR:
    case VTK_PARSE_UNSIGNED_CHAR_PTR:
      fprintf(fp, "unsigned char*");
      break;
    case VTK_PARSE_BOOL_PTR:
      fprintf(fp, "int*");
      break;
    default:
      fprintf(fp, "int");
      break;
  }
}

/* Output local variable declarations for the C++ call */
static void OutputLocalVariableDeclarations(
  FILE* fp, int i, unsigned int aType, const char* Id, int aCount)
{
  /* handle VAR FUNCTIONS */
  if (aType == VTK_PARSE_FUNCTION)
  {
    return;
  }

  /* ignore void */
  if ((aType & VTK_PARSE_UNQUALIFIED_TYPE) == VTK_PARSE_VOID)
  {
    return;
  }

  /* for const * return types prototype with const */
  if ((i == MAX_ARGS) && ((aType & VTK_PARSE_INDIRECT) != 0) && ((aType & VTK_PARSE_CONST) != 0))
  {
    fprintf(fp, "  const ");
  }
  else
  {
    fprintf(fp, "  ");
  }

  if ((aType & VTK_PARSE_UNSIGNED) != 0)
  {
    fprintf(fp, "unsigned ");
  }

  switch ((aType & VTK_PARSE_BASE_TYPE) & ~VTK_PARSE_UNSIGNED)
  {
    case VTK_PARSE_FLOAT:
      fprintf(fp, "float ");
      break;
    case VTK_PARSE_DOUBLE:
      fprintf(fp, "double ");
      break;
    case VTK_PARSE_INT:
      fprintf(fp, "int ");
      break;
    case VTK_PARSE_SHORT:
      fprintf(fp, "short ");
      break;
    case VTK_PARSE_LONG:
      fprintf(fp, "long ");
      break;
    case VTK_PARSE_VOID:
      fprintf(fp, "void ");
      break;
    case VTK_PARSE_CHAR:
      fprintf(fp, "char ");
      break;
    case VTK_PARSE_LONG_LONG:
      fprintf(fp, "long long ");
      break;
    case VTK_PARSE_SIGNED_CHAR:
      fprintf(fp, "signed char ");
      break;
    case VTK_PARSE_BOOL:
      fprintf(fp, "bool ");
      break;
    case VTK_PARSE_OBJECT:
      fprintf(fp, "%s ", Id);
      break;
    case VTK_PARSE_STRING:
      fprintf(fp, "%s ", Id);
      break;
    case VTK_PARSE_UNKNOWN:
      fprintf(fp, "%s ", Id);
      break;
  }

  int FunctionReturnsObjectOrString = (i == MAX_ARGS) ||
    ((aType & VTK_PARSE_UNQUALIFIED_TYPE) == VTK_PARSE_OBJECT_PTR) ||
    ((aType & VTK_PARSE_UNQUALIFIED_TYPE) == VTK_PARSE_CHAR_PTR);

  switch (aType & VTK_PARSE_INDIRECT)
  {
    case VTK_PARSE_REF:
      if (i == MAX_ARGS)
      {
        fprintf(fp, "* "); /* act as & */
      }
      break;
    case VTK_PARSE_POINTER:
      if (FunctionReturnsObjectOrString)
      {
        fprintf(fp, "* ");
      }
      break;
    default:
      fprintf(fp, "  ");
      break;
  }
  fprintf(fp, "temp%i", i);

  /* handle arrays */
  if (((aType & VTK_PARSE_INDIRECT) == VTK_PARSE_POINTER) && !FunctionReturnsObjectOrString)
  {
    fprintf(fp, "[%i]", aCount);
  }

  fprintf(fp, ";\n");
}

/* Output local variable assignments converting C types to C++ types */
static void OutputLocalVariableAssignments(FILE* fp, int i)
{
  unsigned int rawType = thisFunction->ArgTypes[i];

  /* handle VAR FUNCTIONS */
  if (rawType == VTK_PARSE_FUNCTION)
  {
    return;
  }

  unsigned int basicType = rawType & VTK_PARSE_UNQUALIFIED_TYPE;
  /* ignore void */
  if (basicType == VTK_PARSE_VOID)
  {
    return;
  }

  switch (basicType)
  {
    case VTK_PARSE_CHAR:
      fprintf(fp, "  temp%i = static_cast<char>(id%i);\n", i, i);
      break;
    case VTK_PARSE_BOOL:
      fprintf(fp, "  temp%i = (id%i != 0) ? true : false;\n", i, i);
      break;
    case VTK_PARSE_CHAR_PTR:
      /* string passed directly as const char* */
      fprintf(fp, "  temp%i = const_cast<char*>(id%i);\n", i, i);
      break;
    case VTK_PARSE_STRING:
    case VTK_PARSE_STRING_REF:
      fprintf(fp, "  temp%i = id%i;\n", i, i);
      break;
    case VTK_PARSE_OBJECT_PTR:
      fprintf(fp, "  temp%i = static_cast<%s*>(id%i);\n", i, thisFunction->ArgClasses[i], i);
      break;
    case VTK_PARSE_FLOAT_PTR:
    case VTK_PARSE_DOUBLE_PTR:
    case VTK_PARSE_INT_PTR:
    case VTK_PARSE_UNSIGNED_INT_PTR:
    case VTK_PARSE_SHORT_PTR:
    case VTK_PARSE_UNSIGNED_SHORT_PTR:
    case VTK_PARSE_SIGNED_CHAR_PTR:
    case VTK_PARSE_UNSIGNED_CHAR_PTR:
    case VTK_PARSE_LONG_PTR:
    case VTK_PARSE_UNSIGNED_LONG_PTR:
    case VTK_PARSE_LONG_LONG_PTR:
    case VTK_PARSE_UNSIGNED_LONG_LONG_PTR:
    case VTK_PARSE_BOOL_PTR:
      /* arrays are passed directly as pointers from pinned C# arrays */
      fprintf(fp, "  memcpy(temp%i, id%i, %i * sizeof(temp%i[0]));\n", i, i,
        thisFunction->Parameters[i]->Count, i);
      break;
    case VTK_PARSE_UNKNOWN:
      fprintf(fp, "  temp%i = static_cast<%s>(id%i);\n", i, thisFunction->ArgClasses[i], i);
      break;
    case VTK_PARSE_VOID:
    case VTK_PARSE_OBJECT:
    case VTK_PARSE_OBJECT_REF:
      break;
    default:
      fprintf(fp, "  temp%i = id%i;\n", i, i);
      break;
  }
}

/* Copy back modified array data */
static void OutputCopyBackArrays(FILE* fp, int i)
{
  unsigned int rawType = thisFunction->ArgTypes[i];

  if (rawType == VTK_PARSE_FUNCTION)
  {
    return;
  }

  unsigned int basicType = rawType & VTK_PARSE_UNQUALIFIED_TYPE;
  if (basicType == VTK_PARSE_VOID)
  {
    return;
  }

  /* only copy back for non-const arrays */
  if ((rawType & VTK_PARSE_CONST) == 0)
  {
    switch (basicType)
    {
      case VTK_PARSE_FLOAT_PTR:
      case VTK_PARSE_DOUBLE_PTR:
      case VTK_PARSE_INT_PTR:
      case VTK_PARSE_UNSIGNED_INT_PTR:
      case VTK_PARSE_SHORT_PTR:
      case VTK_PARSE_UNSIGNED_SHORT_PTR:
      case VTK_PARSE_SIGNED_CHAR_PTR:
      case VTK_PARSE_UNSIGNED_CHAR_PTR:
      case VTK_PARSE_LONG_PTR:
      case VTK_PARSE_UNSIGNED_LONG_PTR:
      case VTK_PARSE_LONG_LONG_PTR:
      case VTK_PARSE_UNSIGNED_LONG_LONG_PTR:
      case VTK_PARSE_BOOL_PTR:
        fprintf(fp, "  memcpy(id%i, temp%i, %i * sizeof(temp%i[0]));\n", i, i,
          thisFunction->Parameters[i]->Count, i);
        break;
      default:
        break;
    }
  }
}

/* Output the return statement */
static void OutputFunctionResult(FILE* fp)
{
  unsigned int rType = (thisFunction->ReturnType & VTK_PARSE_UNQUALIFIED_TYPE);

  if (rType == VTK_PARSE_VOID)
  {
    return;
  }

  switch (rType)
  {
    case VTK_PARSE_OBJECT_PTR:
      fprintf(fp, "  return static_cast<void*>(temp%i);\n", MAX_ARGS);
      break;

    case VTK_PARSE_STRING:
    {
      /* std::string return: use thread-local static to ensure pointer lifetime */
      fprintf(fp, "  static thread_local std::string _cs_result;\n");
      fprintf(fp, "  _cs_result = temp%i;\n", MAX_ARGS);
      fprintf(fp, "  return _cs_result.c_str();\n");
      break;
    }

    case VTK_PARSE_STRING_REF:
    {
      fprintf(fp, "  return temp%i->c_str();\n", MAX_ARGS);
      break;
    }

    case VTK_PARSE_CHAR_PTR:
    {
      if (thisFunction->ReturnValue->Count > 0)
      {
        /* has a size hint, return as pointer directly */
        fprintf(fp, "  return temp%i;\n", MAX_ARGS);
      }
      else
      {
        fprintf(fp, "  return temp%i;\n", MAX_ARGS);
      }
      break;
    }

    /* pointer return types: cast to match extern "C" signature type */
    case VTK_PARSE_FLOAT_PTR:
    case VTK_PARSE_DOUBLE_PTR:
    case VTK_PARSE_INT_PTR:
    case VTK_PARSE_UNSIGNED_INT_PTR:
    case VTK_PARSE_SHORT_PTR:
    case VTK_PARSE_UNSIGNED_SHORT_PTR:
    case VTK_PARSE_LONG_LONG_PTR:
    case VTK_PARSE_UNSIGNED_LONG_LONG_PTR:
      fprintf(fp, "  return temp%i;\n", MAX_ARGS);
      break;
    case VTK_PARSE_LONG_PTR:
    case VTK_PARSE_UNSIGNED_LONG_PTR:
      /* long may differ from long long on some platforms; cast to match signature */
      fprintf(fp, "  return reinterpret_cast<long long*>(temp%i);\n", MAX_ARGS);
      break;
    case VTK_PARSE_SIGNED_CHAR_PTR:
      /* signed char* needs cast to unsigned char* to match extern C signature */
      fprintf(fp, "  return reinterpret_cast<unsigned char*>(temp%i);\n", MAX_ARGS);
      break;
    case VTK_PARSE_UNSIGNED_CHAR_PTR:
    case VTK_PARSE_BOOL_PTR:
      fprintf(fp, "  return temp%i;\n", MAX_ARGS);
      break;

    case VTK_PARSE_BOOL:
      fprintf(fp, "  return static_cast<int>(temp%i);\n", MAX_ARGS);
      break;

    case VTK_PARSE_UNKNOWN: /* enum */
      fprintf(fp, "  return static_cast<int>(temp%i);\n", MAX_ARGS);
      break;

    default:
      fprintf(fp, "  return temp%i;\n", MAX_ARGS);
      break;
  }
}

/* Check to see if two types will map to the same C# type,
 * return 1 if type1 should take precedence,
 * return 2 if type2 should take precedence,
 * return 0 if the types do not map to the same type */
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
      if (strcmp(c1, c2) == 0)
      {
        return 1;
      }
      return 0;
    }
    else
    {
      return 1;
    }
  }

  for (i = 0; numericTypes[i]; i++)
  {
    hit1 = 0;
    hit2 = 0;
    for (j = 0; numericTypes[i][j]; j++)
    {
      if ((type1 & VTK_PARSE_BASE_TYPE) == numericTypes[i][j])
      {
        hit1 = j + 1;
      }
      if ((type2 & VTK_PARSE_BASE_TYPE) == numericTypes[i][j])
      {
        hit2 = j + 1;
      }
    }
    if (hit1 && hit2 && (type1 & VTK_PARSE_INDIRECT) == (type2 & VTK_PARSE_INDIRECT))
    {
      if (hit1 < hit2)
      {
        return 1;
      }
      else
      {
        return 2;
      }
    }
  }

  hit1 = 0;
  hit2 = 0;
  for (j = 0; stringTypes[j]; j++)
  {
    if ((type1 & VTK_PARSE_UNQUALIFIED_TYPE) == stringTypes[j])
    {
      hit1 = j + 1;
    }
    if ((type2 & VTK_PARSE_UNQUALIFIED_TYPE) == stringTypes[j])
    {
      hit2 = j + 1;
    }
  }
  if (hit1 && hit2)
  {
    if (hit1 < hit2)
    {
      return 1;
    }
    else
    {
      return 2;
    }
  }

  return 0;
}

/* have we done one of these yet */
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
        {
          match = 0;
        }
      }
      if (!CheckMatch(
            thisFunction->ReturnType, fi->ReturnType, thisFunction->ReturnClass, fi->ReturnClass))
      {
        match = 0;
      }
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

    if (entry == 0 || !vtkParseHierarchy_IsTypeOf(hierarchyInfo, entry, "vtkObjectBase"))
    {
      return 0;
    }
  }

  /* Templated classes are not wrapped */
  if (strchr(classname, '<'))
  {
    return 0;
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

  /* some functions will not get wrapped no matter what */
  if (thisFunction->IsOperator || thisFunction->ArrayFailure || thisFunction->Template ||
    thisFunction->IsExcluded || thisFunction->IsDeleted || !thisFunction->IsPublic ||
    !thisFunction->Name)
  {
    return 0;
  }

  /* NewInstance and SafeDownCast cannot be wrapped because they return
     a pointer of the same type as the current pointer */
  if (!strcmp("NewInstance", thisFunction->Name))
  {
    return 0;
  }

  if (!strcmp("SafeDownCast", thisFunction->Name))
  {
    return 0;
  }

  /* function pointer arguments for callbacks */
  if (thisFunction->NumberOfArguments == 2 && thisFunction->ArgTypes[0] == VTK_PARSE_FUNCTION &&
    thisFunction->ArgTypes[1] == VTK_PARSE_VOID_PTR && rType == VTK_PARSE_VOID)
  {
    return 1;
  }

  /* check to see if we can handle the args */
  for (i = 0; i < thisFunction->NumberOfArguments; i++)
  {
    aType = (thisFunction->ArgTypes[i] & VTK_PARSE_UNQUALIFIED_TYPE);
    baseType = (aType & VTK_PARSE_BASE_TYPE);

    for (j = 0; supported_types[j] != 0; j++)
    {
      if (baseType == supported_types[j])
      {
        break;
      }
    }
    if (supported_types[j] == 0)
    {
      args_ok = 0;
    }

    if (baseType == VTK_PARSE_UNKNOWN)
    {
      const char* qualified_name = 0;
      if ((aType & VTK_PARSE_INDIRECT) == 0)
      {
        qualified_name = vtkParseHierarchy_QualifiedEnumName(
          hierarchyInfo, data, stringCache, thisFunction->ArgClasses[i]);
      }
      if (qualified_name)
      {
        thisFunction->ArgClasses[i] = qualified_name;
      }
      else
      {
        args_ok = 0;
      }
    }

    if (baseType == VTK_PARSE_OBJECT)
    {
      if ((aType & VTK_PARSE_INDIRECT) != VTK_PARSE_POINTER)
      {
        args_ok = 0;
      }
      else if (!isClassWrapped(thisFunction->ArgClasses[i]))
      {
        args_ok = 0;
      }
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
    {
      break;
    }
  }
  if (supported_types[j] == 0)
  {
    args_ok = 0;
  }

  if (baseType == VTK_PARSE_UNKNOWN)
  {
    const char* qualified_name = 0;
    if ((rType & VTK_PARSE_INDIRECT) == 0)
    {
      qualified_name = vtkParseHierarchy_QualifiedEnumName(
        hierarchyInfo, data, stringCache, thisFunction->ReturnClass);
    }
    if (qualified_name)
    {
      thisFunction->ReturnClass = qualified_name;
    }
    else
    {
      args_ok = 0;
    }
  }

  if (baseType == VTK_PARSE_OBJECT)
  {
    if ((rType & VTK_PARSE_INDIRECT) != VTK_PARSE_POINTER)
    {
      args_ok = 0;
    }
    else if (!isClassWrapped(thisFunction->ReturnClass))
    {
      args_ok = 0;
    }
  }

  if (((rType & VTK_PARSE_INDIRECT) != VTK_PARSE_POINTER) && ((rType & VTK_PARSE_INDIRECT) != 0) &&
    (rType != VTK_PARSE_STRING_REF))
    args_ok = 0;
  if (rType == VTK_PARSE_STRING_PTR)
    args_ok = 0;

  /* eliminate unsigned pointer returns */
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

  /* make sure we have all the info we need for array arguments */
  for (i = 0; i < thisFunction->NumberOfArguments; i++)
  {
    aType = (thisFunction->ArgTypes[i] & VTK_PARSE_UNQUALIFIED_TYPE);

    if (((aType & VTK_PARSE_INDIRECT) == VTK_PARSE_POINTER) &&
      (thisFunction->Parameters[i]->Count <= 0) && (aType != VTK_PARSE_OBJECT_PTR) &&
      (aType != VTK_PARSE_CHAR_PTR))
      args_ok = 0;
  }

  /* if we need a return type hint make sure we have one */
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

  /* make sure there isn't a C#-specific override */
  if (!strcmp("vtkObject", data->Name))
  {
    /* remove the original vtkCommand observer methods */
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
    /* remove the special vtkObjectBase methods */
    if (!strcmp(thisFunction->Name, "Print"))
    {
      args_ok = 0;
    }
  }

  /* make sure it isn't a Delete or New function */
  if (!strcmp("Delete", thisFunction->Name) || !strcmp("New", thisFunction->Name))
  {
    args_ok = 0;
  }

  return args_ok;
}

static void outputFunction(FILE* fp, ClassInfo* data)
{
  int i;
  int args_ok;
  unsigned int rType = (thisFunction->ReturnType & VTK_PARSE_UNQUALIFIED_TYPE);
  thisClass = data;

  args_ok = checkFunctionSignature(data);

  if (!thisFunction->IsExcluded && thisFunction->IsPublic && args_ok &&
    strcmp(data->Name, thisFunction->Name) != 0 && strcmp(data->Name, thisFunction->Name + 1) != 0)
  {
    /* make sure we haven't already done one of these */
    if (!DoneOne())
    {
      fprintf(fp, "\nextern \"C\" VTK_CSHARP_EXPORT ");
      OutputReturnType(fp);
      fprintf(fp, " %s_%s_%i(void* obj", data->Name, thisFunction->Name,
        numberOfWrappedFunctions);

      for (i = 0; i < thisFunction->NumberOfArguments; i++)
      {
        fprintf(fp, ", ");
        OutputParamType(fp, i);

        /* ignore args after function pointer */
        if (thisFunction->ArgTypes[i] == VTK_PARSE_FUNCTION)
        {
          break;
        }
      }
      fprintf(fp, ")\n{\n");

      /* declare local variables */
      for (i = 0; i < thisFunction->NumberOfArguments; i++)
      {
        OutputLocalVariableDeclarations(fp, i, thisFunction->ArgTypes[i],
          thisFunction->ArgClasses[i], thisFunction->ArgCounts[i]);

        if (thisFunction->ArgTypes[i] == VTK_PARSE_FUNCTION)
        {
          break;
        }
      }
      OutputLocalVariableDeclarations(
        fp, MAX_ARGS, thisFunction->ReturnType, thisFunction->ReturnClass, 0);

      /* assign local variables from parameters */
      for (i = 0; i < thisFunction->NumberOfArguments; i++)
      {
        OutputLocalVariableAssignments(fp, i);

        if (thisFunction->ArgTypes[i] == VTK_PARSE_FUNCTION)
        {
          break;
        }
      }

      /* cast the object pointer */
      fprintf(fp, "\n  %s* op = static_cast<%s*>(obj);\n", data->Name, data->Name);

      /* make the C++ call */
      switch (rType)
      {
        case VTK_PARSE_VOID:
          fprintf(fp, "  op->%s(", thisFunction->Name);
          break;
        default:
          if ((rType & VTK_PARSE_INDIRECT) == VTK_PARSE_REF)
          {
            fprintf(fp, "  temp%i = &(op)->%s(", MAX_ARGS, thisFunction->Name);
          }
          else
          {
            fprintf(fp, "  temp%i = op->%s(", MAX_ARGS, thisFunction->Name);
          }
          break;
      }

      for (i = 0; i < thisFunction->NumberOfArguments; i++)
      {
        if (i)
        {
          fprintf(fp, ", ");
        }
        if (thisFunction->ArgTypes[i] == VTK_PARSE_FUNCTION)
        {
          fprintf(fp, "reinterpret_cast<void(*)(void*)>(fptr), clientdata");
          break;
        }
        else
        {
          fprintf(fp, "temp%i", i);
        }
      }

      fprintf(fp, ");\n");

      /* copy back any arrays */
      for (i = 0; i < thisFunction->NumberOfArguments; i++)
      {
        OutputCopyBackArrays(fp, i);

        if (thisFunction->ArgTypes[i] == VTK_PARSE_FUNCTION)
        {
          break;
        }
      }
      OutputFunctionResult(fp);
      fprintf(fp, "}\n");

      wrappedFunctions[numberOfWrappedFunctions] = thisFunction;
      numberOfWrappedFunctions++;
    }
  }
}

/* print the parsed structures */
int VTK_PARSE_MAIN(int argc, char* argv[])
{
  const OptionInfo* options;
  FileInfo* file_info;
  ClassInfo* data;
  FILE* fp;
  int i;

  /* pre-define a macro to identify the language */
  vtkParse_DefineMacro("__VTK_WRAP_CSHARP__", 0);

  /* get command-line args and parse the header file */
  file_info = vtkParse_Main(argc, argv);

  /* some utility functions require the string cache */
  stringCache = file_info->Strings;

  /* get the command-line options */
  options = vtkParse_GetCommandLineOptions();

  /* get the hierarchy info for accurate typing */
  if (options->HierarchyFileNames)
  {
    hierarchyInfo =
      vtkParseHierarchy_ReadFiles(options->NumberOfHierarchyFileNames, options->HierarchyFileNames);
  }

  /* get the output file */
  fp = vtkParse_FileOpen(options->OutputFileName, "w");

  if (!fp)
  {
    fprintf(stderr, "Error opening output file %s\n", options->OutputFileName);
    return vtkParse_FinalizeMain(1);
  }

  /* get the main class */
  data = file_info->MainClass;
  if (data == NULL || data->IsExcluded)
  {
    fclose(fp);
    return vtkParse_FinalizeMain(0);
  }

  if (data->Template)
  {
    fclose(fp);
    vtkWrap_WarnEmpty(options);
    return vtkParse_FinalizeMain(0);
  }

  for (i = 0; i < data->NumberOfSuperClasses; ++i)
  {
    if (strchr(data->SuperClasses[i], '<'))
    {
      fclose(fp);
      vtkWrap_WarnEmpty(options);
      return vtkParse_FinalizeMain(0);
    }
  }

  if (hierarchyInfo)
  {
    if (!vtkWrap_IsTypeOf(hierarchyInfo, data->Name, "vtkObjectBase"))
    {
      fclose(fp);
      vtkWrap_WarnEmpty(options);
      return vtkParse_FinalizeMain(0);
    }

    /* resolve using declarations within the header files */
    vtkWrap_ApplyUsingDeclarations(data, file_info, hierarchyInfo);

    /* expand typedefs */
    vtkWrap_ExpandTypedefs(data, file_info, hierarchyInfo);
  }

  /* file header */
  fprintf(fp, "// C# P/Invoke wrapper for %s object\n//\n", data->Name);
  fprintf(fp, "#define VTK_WRAPPING_CXX\n");
  if (strcmp("vtkObjectBase", data->Name) != 0)
  {
    fprintf(fp, "#define VTK_STREAMS_FWD_ONLY\n");
  }
  fprintf(fp, "#include \"vtkABI.h\"\n");
  fprintf(fp, "#include \"vtkSystemIncludes.h\"\n");
  fprintf(fp, "#include \"%s.h\"\n", data->Name);
  if (!strcmp("vtkObject", data->Name))
  {
    fprintf(fp, "#include \"vtkCallbackCommand.h\"\n");
  }
  fprintf(fp, "#include <cstring>\n");
  fprintf(fp, "#include <string>\n");
  fprintf(fp, "#include <sstream>\n\n");

  OutputExportMacro(fp);

  /* insert function handling code here */
  for (i = 0; i < data->NumberOfFunctions; i++)
  {
    thisFunction = data->Functions[i];
    outputFunction(fp, data);
  }

  /* special vtkObjectBase methods */
  if ((!data->NumberOfSuperClasses) && (data->HasDelete))
  {
    /* VTKDeleteReference - decrement ref count from a raw pointer */
    fprintf(fp, "\nextern \"C\" VTK_CSHARP_EXPORT ");
    fprintf(fp, "void %s_VTKDeleteReference(void* id)\n", data->Name);
    fprintf(fp, "{\n");
    fprintf(fp, "  %s* op = static_cast<%s*>(id);\n", data->Name, data->Name);
    fprintf(fp, "  op->Delete();\n");
    fprintf(fp, "}\n");

    /* VTKGetClassName - get class name from a raw pointer */
    fprintf(fp, "\nextern \"C\" VTK_CSHARP_EXPORT ");
    fprintf(fp, "const char* %s_VTKGetClassName(void* id)\n", data->Name);
    fprintf(fp, "{\n");
    fprintf(fp, "  if (!id) { return \"\"; }\n");
    fprintf(fp, "  %s* op = static_cast<%s*>(id);\n", data->Name, data->Name);
    fprintf(fp, "  return op->GetClassName();\n");
    fprintf(fp, "}\n");

    /* VTKDelete - Delete from object */
    fprintf(fp, "\nextern \"C\" VTK_CSHARP_EXPORT ");
    fprintf(fp, "void %s_VTKDelete(void* obj)\n", data->Name);
    fprintf(fp, "{\n");
    fprintf(fp, "  %s* op = static_cast<%s*>(obj);\n", data->Name, data->Name);
    fprintf(fp, "  op->Delete();\n");
    fprintf(fp, "}\n");

    /* VTKRegister - increment ref count */
    fprintf(fp, "\nextern \"C\" VTK_CSHARP_EXPORT ");
    fprintf(fp, "void %s_VTKRegister(void* obj)\n", data->Name);
    fprintf(fp, "{\n");
    fprintf(fp, "  %s* op = static_cast<%s*>(obj);\n", data->Name, data->Name);
    fprintf(fp, "  op->Register(op);\n");
    fprintf(fp, "}\n");
  }

  /* New() for non-abstract classes */
  if (!data->IsAbstract)
  {
    fprintf(fp, "\nextern \"C\" VTK_CSHARP_EXPORT ");
    fprintf(fp, "void* %s_New(void)", data->Name);
    fprintf(fp, "\n{\n");
    fprintf(fp, "  return static_cast<void*>(%s::New());\n", data->Name);
    fprintf(fp, "}\n");
  }

  /* vtkObjectBase: Print method */
  if (!strcmp("vtkObjectBase", data->Name))
  {
    fprintf(fp, "\nextern \"C\" VTK_CSHARP_EXPORT ");
    fprintf(fp, "const char* vtkObjectBase_Print(void* obj)\n");
    fprintf(fp, "{\n");
    fprintf(fp, "  vtkObjectBase* op = static_cast<vtkObjectBase*>(obj);\n");
    fprintf(fp, "  static thread_local std::string _cs_print_result;\n");
    fprintf(fp, "  std::ostringstream stream;\n");
    fprintf(fp, "  op->Print(stream);\n");
    fprintf(fp, "  _cs_print_result = stream.str();\n");
    fprintf(fp, "  return _cs_print_result.c_str();\n");
    fprintf(fp, "}\n");
  }

  /* vtkObject: AddObserver with function pointer callback */
  if (!strcmp("vtkObject", data->Name))
  {
    fprintf(fp, "\n/* Callback bridge for C# delegates */\n");
    fprintf(fp, "typedef void (*VtkCSharpCallbackFunc)(void* clientData);\n\n");

    fprintf(fp, "static void vtkCSharpCallbackBridge(\n");
    fprintf(fp, "  vtkObject* vtkNotUsed(caller), unsigned long vtkNotUsed(eid),\n");
    fprintf(fp, "  void* clientData, void* vtkNotUsed(calldata))\n");
    fprintf(fp, "{\n");
    fprintf(fp, "  VtkCSharpCallbackFunc func = "
                "reinterpret_cast<VtkCSharpCallbackFunc>(clientData);\n");
    fprintf(fp, "  if (func) { func(nullptr); }\n");
    fprintf(fp, "}\n\n");

    fprintf(fp, "extern \"C\" VTK_CSHARP_EXPORT ");
    fprintf(fp, "unsigned long long vtkObject_AddObserverCSharp(\n");
    fprintf(fp, "  void* obj, const char* event, void* callbackPtr)\n");
    fprintf(fp, "{\n");
    fprintf(fp, "  vtkObject* op = static_cast<vtkObject*>(obj);\n");
    fprintf(fp, "  vtkCallbackCommand* cmd = vtkCallbackCommand::New();\n");
    fprintf(fp, "  cmd->SetClientData(callbackPtr);\n");
    fprintf(fp, "  cmd->SetCallback(vtkCSharpCallbackBridge);\n");
    fprintf(fp, "  unsigned long result = op->AddObserver(event, cmd);\n");
    fprintf(fp, "  cmd->Delete();\n");
    fprintf(fp, "  return static_cast<unsigned long long>(result);\n");
    fprintf(fp, "}\n");

    fprintf(fp, "\nextern \"C\" VTK_CSHARP_EXPORT ");
    fprintf(fp, "void vtkObject_RemoveObserverCSharp(void* obj, unsigned long long tag)\n");
    fprintf(fp, "{\n");
    fprintf(fp, "  vtkObject* op = static_cast<vtkObject*>(obj);\n");
    fprintf(fp, "  op->RemoveObserver(static_cast<unsigned long>(tag));\n");
    fprintf(fp, "}\n");
  }

  if (hierarchyInfo)
  {
    vtkParseHierarchy_Free(hierarchyInfo);
  }

  vtkParse_Free(file_info);

  fclose(fp);

  return vtkParse_FinalizeMain(0);
}

// NOLINTEND(bugprone-unsafe-functions)
