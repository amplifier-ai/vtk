# VTK C# Bindings: Исследование и архитектурный анализ

> Дата: 2026-02-19
> Цель: Исследовать существующие биндинги VTK (Python, Java), предложить архитектуру для C#

---

## 1. Общая инфраструктура обёрток VTK

VTK использует единую инфраструктуру парсинга для всех языков. Все инструменты написаны на C и собираются в библиотеку `VTK::WrappingTools`.

### Пайплайн генерации

```
C++ Header (.h)
      │
      ▼
┌─────────────────────────┐
│  vtkParse (lex/yacc)     │  ← Парсер C++ заголовков
│  IR: FileInfo/ClassInfo/  │
│      FunctionInfo/ValueInfo│
└─────────────────────────┘
      │
      ▼
┌─────────────────────────┐
│  vtkParseHierarchy       │  ← Граф наследования между модулями
│  vtkWrap.*               │  ← Общие утилиты классификации типов
└─────────────────────────┘
      │
      ├──► vtkWrapPython*.c      → CPython .cxx glue code
      ├──► vtkWrapJava.c         → JNI .cxx glue code
      ├──► vtkParseJava.c        → .java source files
      ├──► vtkWrapSerDes*.c      → JSON serializer
      └──► vtkWrapJavaScript*.c  → Emscripten/embind
```

### Ключевые файлы общей инфраструктуры

| Файл | Назначение |
|------|------------|
| `Wrapping/Tools/vtkParse.y` | Bison GLR-грамматика для C++ заголовков |
| `Wrapping/Tools/vtkParse.l` | Flex лексер |
| `Wrapping/Tools/vtkParseData.h` | IR-структуры: `FileInfo`, `ClassInfo`, `FunctionInfo`, `ValueInfo` |
| `Wrapping/Tools/vtkParseType.h` | 32-битная кодировка типов (base type + indirection + qualifiers) |
| `Wrapping/Tools/vtkParseHierarchy.h` | `HierarchyInfo`/`HierarchyEntry` — межмодульное наследование |
| `Wrapping/Tools/vtkParsePreprocess.c` | Встроенный C-препроцессор |
| `Wrapping/Tools/vtkParseMerge.c` | Слияние методов суперклассов в `ClassInfo` |
| `Wrapping/Tools/vtkParseProperties.c` | Обнаружение Get/Set пар как "свойств" |
| `Wrapping/Tools/vtkParseAttributes.c` | Обработка `[[vtk::...]]` атрибутов |
| `Wrapping/Tools/vtkWrap.h/c` | Предикаты классификации типов (`vtkWrap_IsVTKObject`, `vtkWrap_IsArray`, и т.д.) |
| `Wrapping/Tools/vtkWrapText.h/c` | Форматирование документации и сигнатур |
| `Wrapping/Tools/vtkWrapHierarchy.c` | Генератор `.hierarchy` файлов |
| `Wrapping/Tools/vtkParseMain.c` | Общий CLI для всех wrapper-инструментов |
| `Common/Core/vtkWrappingHints.h` | Макросы подсказок: `VTK_WRAPEXCLUDE`, `VTK_NEWINSTANCE`, `VTK_SIZEHINT`, и т.д. |

### IR-структура (дерево разбора)

```
FileInfo
  └─ NamespaceInfo (Contents)   -- глобальное пространство имён
       ├─ ClassInfo[]            -- классы/структуры
       │    ├─ FunctionInfo[]    -- методы
       │    │    ├─ ValueInfo[]  -- параметры
       │    │    └─ ValueInfo    -- возвращаемое значение
       │    ├─ ValueInfo[]       -- константы, переменные, typedef-ы
       │    ├─ ClassInfo[]       -- вложенные классы
       │    └─ ClassInfo[]       -- enum-ы (тот же struct, ItemType=VTK_ENUM_INFO)
       ├─ FunctionInfo[]         -- свободные функции
       └─ NamespaceInfo[]        -- вложенные пространства имён
```

### Подсказки для обёрток (`vtkWrappingHints.h`)

| Макрос | Атрибут | Эффект |
|--------|---------|--------|
| `VTK_WRAPEXCLUDE` | `[[vtk::wrapexclude]]` | Пропустить метод/класс |
| `VTK_NEWINSTANCE` | `[[vtk::newinstance]]` | Возвращаемое значение передаёт владение |
| `VTK_ZEROCOPY` | `[[vtk::zerocopy]]` | Передать указатель на буфер без копирования |
| `VTK_FILEPATH` | `[[vtk::filepath]]` | Параметр — путь к файлу |
| `VTK_UNBLOCKTHREADS` | `[[vtk::unblockthreads]]` | Отпустить GIL перед вызовом |
| `VTK_EXPECTS(x)` | `[[vtk::expects(x)]]` | Предусловие |
| `VTK_SIZEHINT(...)` | `[[vtk::sizehint(...)]]` | Подсказка размера массива |

---

## 2. Python-биндинг: архитектура

### Компоненты

| Компонент | Директория | Назначение |
|-----------|-----------|------------|
| Генераторы кода (12 файлов) | `Wrapping/Tools/vtkWrapPython*.c` | Для каждого `vtkFoo.h` создаёт `vtkFooPython.cxx` |
| Init-генератор | `Wrapping/Tools/vtkWrapPythonInit.c` | Генерирует `PyInit_<Module>()` |
| Runtime-библиотека (~15 файлов) | `Wrapping/PythonCore/` | `PyVTKObject`, `vtkPythonArgs`, `vtkPythonUtil` |
| Python-пакет | `Wrapping/Python/vtkmodules/` | `__init__.py`, `.pyi` стабы, GUI-обёртки |
| CMake | `CMake/vtkModuleWrapPython.cmake` | Оркестрация сборки |

### Генераторы кода (Wrapping/Tools/)

| Файл | Что генерирует |
|------|---------------|
| `vtkWrapPython.c` | Точка входа, вызывает `vtkParse_Main()` и диспатчит в суб-генераторы |
| `vtkWrapPythonClass.c` | Регистрация классов, `PyVTKClass_Add()`, фабричные `PyClassNew()` |
| `vtkWrapPythonMethod.c` | Обёртки методов: извлечение аргументов через `vtkPythonArgs`, вызов C++, конверсия результата |
| `vtkWrapPythonMethodDef.c` | Таблицы `PyMethodDef` |
| `vtkWrapPythonOverload.c` | Строки type-signature для разрешения перегрузок |
| `vtkWrapPythonType.c` | "Специальные типы" (не `vtkObjectBase`): `__str__`, `__hash__`, `[]` |
| `vtkWrapPythonEnum.c` | Enum-ы как подтипы `int` |
| `vtkWrapPythonConstant.c` | Константы уровня модуля |
| `vtkWrapPythonNamespace.c` | C++ namespace-ы как Python-модули |
| `vtkWrapPythonTemplate.c` | C++ шаблоны как dict-подобные объекты |
| `vtkWrapPythonProperty.c` | PascalCase → snake_case `PyGetSetDef` для Get/Set пар |
| `vtkWrapPythonNumberProtocol.c` | Арифметические/сравнительные операторы |

### Runtime-слой (Wrapping/PythonCore/)

| Файл | Назначение |
|------|------------|
| `PyVTKObject.h/cxx` | Python-тип для `vtkObjectBase` подклассов. Struct: `PyObject_HEAD` + `vtk_ptr` + `vtk_dict` + `vtk_flags` |
| `PyVTKSpecialObject.h/cxx` | Python-тип для не-`vtkObjectBase` классов (по значению, copy-construct) |
| `PyVTKEnum.h/cxx` | Python-тип для C++ enum-ов |
| `PyVTKTemplate.h/cxx` | Контейнер для инстанцирований шаблонов |
| `PyVTKNamespace.h/cxx` | Python-модуль для C++ namespace-ов |
| `PyVTKReference.h/cxx` | Симуляция pass-by-reference |
| `PyVTKMethodDescriptor.h/cxx` | Дескриптор для поиска/диспатча методов |
| `vtkPythonUtil.h/cxx` | Центральный singleton: 9 map-ов (ObjectMap, ClassMap, EnumMap, и т.д.) |
| `vtkPythonArgs.h/cxx` | Конверсия аргументов Python → C++ (типизированная, без format string) |
| `vtkPythonOverload.h/cxx` | Runtime-разрешение перегрузок через scoring |
| `vtkPythonCommand.h/cxx` | Python-колбэки как `vtkCommand` observers |
| `vtkSmartPyObject.h` | C++ smart pointer для Python-объектов |

### Ключевые механизмы

**Dual reference counting:**
- VTK `Register()`/`Delete()` + Python `Py_INCREF`/`Py_DECREF`
- `vtkPythonUtil::ObjectMap` (`std::map<vtkObjectBase*, pair<PyObject*, atomic<int32_t>>>`) — один VTK reference на Python-обёртку

**Object identity:**
- `vtkPythonUtil::GetObjectFromPointer()` — проверяет ObjectMap, возвращает существующую обёртку или создаёт новую
- Гарантия: один C++ объект = один Python-объект

**Overload resolution:**
- В `ml_doc` поле `PyMethodDef` хранятся компактные type-signature строки
- `vtkPythonOverload::CallMethod()` итерирует кандидатов, scoring через `CheckArg()`, вызывает лучший

**GIL management:**
- `VTK_UNBLOCKTHREADS` на методе → генератор добавляет `Py_BEGIN_ALLOW_THREADS` / `Py_END_ALLOW_THREADS`

---

## 3. Java-биндинг: архитектура

### Компоненты

| Компонент | Файлы | Назначение |
|-----------|-------|------------|
| JNI-генератор | `Wrapping/Tools/vtkWrapJava.c` | Для каждого `vtkFoo.h` создаёт `vtkFooJava.cxx` (JNI C++ bridge) |
| Java-генератор | `Wrapping/Tools/vtkParseJava.c` | Для каждого `vtkFoo.h` создаёт `vtkFoo.java` |
| Runtime C++ | `Utilities/Java/vtkJavaUtil.h/cxx` | Извлечение указателей, конверсия массивов, колбэки |
| JAWT-интеграция | `Utilities/Java/vtkJavaAwt.h` | Встраивание VTK в AWT canvas |
| Runtime Java | `Wrapping/Java/vtk/*.java` | Memory manager, GC, AWT-компоненты |
| CMake | `CMake/vtkModuleWrapJava.cmake` | Оркестрация |

### Пайплайн сборки

```
vtkFoo.h ──► vtkWrapJava  ──► vtkFooJava.cxx  ──┐
         ──► vtkParseJava ──► vtkFoo.java  ──────┤
                                                  ▼
                                    vtkRenderingCoreJava.so  (JNI shared lib)
                                    vtk.jar                  (Java classes)
```

### Pointer Bridge (центральный механизм)

C++ указатель хранится как `long vtkId` в Java-объекте:

```cpp
// vtkJavaUtil.cxx — извлечение указателя
JNIEXPORT void* vtkJavaGetPointerFromObject(JNIEnv* env, jobject obj) {
    jfieldID id = env->GetFieldID(env->GetObjectClass(obj), "vtkId", "J");
    return (void*)(size_t)env->GetLongField(obj, id);
}
```

```java
// Генерируемый Java-код — возврат объекта
long temp = MethodName_N(...);
if (temp == 0) return null;
return (ReturnClass) vtkObjectBase.JAVA_OBJECT_MANAGER.getJavaObject(temp);
```

### Memory Management

**`vtkJavaMemoryManagerImpl.java`:**
- `HashMap<Long, WeakReference<vtkObjectBase>>` — object identity map
- `getJavaObject(Long vtkId)` — ищет существующую обёртку, если нет — создаёт через reflection (`Class.forName("vtk." + className)`)
- `gc(boolean debug)` — sweep map, вызов C++ `Delete()` для собранных объектов

**`vtkJavaGarbageCollector.java`:**
- `ScheduledExecutorService` → `System.gc()` → `JAVA_OBJECT_MANAGER.gc()` через `SwingUtilities.invokeLater()`

### Typecast Chain

Для каждого класса генерируется C-функция:
```cpp
extern "C" void* vtkActor_Typecast(void* me, char* dType) {
    if (!strcmp("vtkActor", dType)) return me;
    if ((res = vtkProp3D_Typecast(me, dType)) != nullptr) return res;
    return nullptr;
}
```

### Ограничения Java-биндинга

- `NewInstance`, `SafeDownCast` исключены (конфликт static/virtual)
- Множественное наследование C++ усечено до single inheritance
- Шаблонные классы не оборачиваются
- JNI method numbers (`GetBounds_3`) хрупки при изменении порядка методов в заголовке

---

## 4. Сравнительная таблица

| Аспект | Python | Java |
|--------|--------|------|
| **FFI-механизм** | CPython C API | JNI |
| **Хранение указателя** | `PyVTKObject.vtk_ptr` (C struct поле) | `long vtkId` (Java field, JNI reflection) |
| **Reference counting** | Dual (VTK + Python refcount) | VTK refcount + WeakReference GC |
| **Object identity** | `std::map<vtkObjectBase*, PyObject*>` в C++ | `HashMap<Long, WeakReference>` в Java |
| **Overload resolution** | Runtime scoring в C++ | Numbered methods (`_3`, `_7`) — нет runtime overload |
| **Колбэки** | `vtkPythonCommand` (хранит `PyObject*`) | `vtkJavaCommand` (хранит `JavaVM*` + `jobject` + `jmethodID`) |
| **Массивы** | NumPy buffer protocol + `VTK_ZEROCOPY` | `GetXxxArrayRegion()` — всегда копия |
| **Enum-ы** | Python int subtypes | Java int |
| **Properties** | `PyGetSetDef` (snake_case) | Нет (только Get/Set методы) |
| **Генератор** | 12 C-файлов (~5000 строк) | 2 C-файла (~2800 строк) |
| **Runtime** | ~15 C++ файлов (~6000 строк) | ~200 строк C++ + ~500 строк Java |

---

## 5. Предложение для C#: C++/CLI (Windows-only)

### Почему C++/CLI

Решено ограничиться Windows. C++/CLI даёт прямой доступ к C++ без промежуточного C-слоя:

| Преимущество | Описание |
|-------------|----------|
| Нет C-экспортного слоя | Прямой вызов C++ методов из managed-кода |
| Нет маршалинга | Автоматическая конверсия типов компилятором |
| Меньше кода | ~1900 строк вместо ~4600 для P/Invoke |
| Нативные C# properties | Естественный маппинг VTK Get/Set пар |
| `dynamic_cast` | Вместо typecast chain |

### Ограничения C++/CLI

- Только **Windows + MSVC**
- .NET Framework или .NET 5+ (поддержка с VS 2019 16.8)
- ARM64 Windows — с VS 2022 17.3
- Компиляция с `/clr` чуть медленнее

### Архитектура

```
vtkFoo.h ──► vtkParseCSharpCLI.c ──► vtkFoo.cpp  (mixed-mode C++/CLI)
                                          │
                                          ▼
                                   vtkRenderingCoreCSharp.dll  (managed assembly)
```

Один генератор вместо двух. Нет промежуточного C-слоя.

### Структура файлов

```
vtk/
├── Wrapping/
│   ├── Tools/
│   │   └── vtkParseCSharpCLI.c       # Генератор .cpp файлов (~1200 строк)
│   ├── CSharpCore/                    # Runtime support (~400 строк)
│   │   ├── vtkObjectBase.cpp          # Базовый managed-класс
│   │   ├── VtkObjectManager.cpp       # Object identity map
│   │   └── VtkEventHandler.cpp        # Делегаты для колбэков
│   └── CSharp/
│       └── CMakeLists.txt             # Сборка .dll/.nupkg
└── CMake/
    └── vtkModuleWrapCSharp.cmake      # CMake-оркестрация (~300 строк)
```

### Генерируемый код: пример

Для `vtkActor.h` генерируется `vtkActor.cpp`:

```cpp
#pragma once
#include "vtkActor.h"

namespace VTK {

    public ref class vtkActor : public vtkProp3D {
    internal:
        vtkActor(::vtkActor* native, bool ownsRef)
            : vtkProp3D(native, ownsRef) {}

        ::vtkActor* GetNative() {
            return static_cast<::vtkActor*>(m_native);
        }

    public:
        vtkActor() : vtkProp3D(::vtkActor::New(), true) {}

        void SetVisibility(int val) {
            GetNative()->SetVisibility(val);
        }

        int GetVisibility() {
            return GetNative()->GetVisibility();
        }

        // C# property
        property int Visibility {
            int get() { return GetNative()->GetVisibility(); }
            void set(int val) { GetNative()->SetVisibility(val); }
        }

        vtkProperty^ GetProperty() {
            ::vtkProperty* p = GetNative()->GetProperty();
            return VtkObjectManager::GetOrCreate<vtkProperty^>(p);
        }

        array<double>^ GetBounds() {
            double* b = GetNative()->GetBounds();
            auto result = gcnew array<double>(6);
            pin_ptr<double> pinned = &result[0];
            memcpy(pinned, b, 6 * sizeof(double));
            return result;
        }
    };
}
```

### Базовый класс: `vtkObjectBase`

```cpp
namespace VTK {

    public ref class vtkObjectBase {
    internal:
        ::vtkObjectBase* m_native;
        bool m_ownsRef;

        vtkObjectBase(::vtkObjectBase* native, bool ownsRef) {
            m_native = native;
            m_ownsRef = ownsRef;
            if (native) VtkObjectManager::Register(this);
        }

    public:
        ~vtkObjectBase() { this->!vtkObjectBase(); }  // IDisposable.Dispose()

        !vtkObjectBase() {  // Destructor
            if (m_native && m_ownsRef) {
                VtkObjectManager::Unregister(m_native);
                m_native->Delete();
                m_native = nullptr;
            }
        }

        System::String^ GetClassName() {
            return gcnew System::String(m_native->GetClassName());
        }
    };
}
```

### Object Identity Manager

```cpp
namespace VTK {
    using namespace System;
    using namespace System::Collections::Concurrent;
    using namespace System::Runtime::InteropServices;

    private ref class VtkObjectManager {
        static ConcurrentDictionary<IntPtr, WeakReference^>^ _map =
            gcnew ConcurrentDictionary<IntPtr, WeakReference^>();

    internal:
        generic<typename T> where T : vtkObjectBase
        static T GetOrCreate(::vtkObjectBase* ptr) {
            if (!ptr) return T();
            IntPtr key(ptr);
            WeakReference^ weakRef;
            if (_map->TryGetValue(key, weakRef)) {
                Object^ target = weakRef->Target;
                if (target) return safe_cast<T>(target);
            }
            // Создать новую обёртку; Register() вызывается в конструкторе
            ptr->Register(nullptr);  // AddRef
            // ... reflection для создания правильного конкретного типа
        }

        static void Register(vtkObjectBase^ obj) {
            _map[IntPtr(obj->m_native)] = gcnew WeakReference(obj);
        }

        static void Unregister(::vtkObjectBase* ptr) {
            IntPtr key(ptr);
            WeakReference^ removed;
            _map->TryRemove(key, removed);
        }
    };
}
```

### Колбэки (Observer pattern)

```cpp
public delegate void VtkEventHandler(vtkObject^ sender, unsigned long eventId);

// В генерируемом коде vtkObject:
unsigned long AddObserver(unsigned long event, VtkEventHandler^ handler) {
    auto pin = GCHandle::Alloc(handler);
    auto* cmd = vtkCallbackCommand::New();
    cmd->SetClientData(GCHandle::ToIntPtr(pin).ToPointer());
    cmd->SetCallback(&ManagedCallbackBridge);
    return GetNative()->AddObserver(event, cmd);
}

// Статический bridge:
static void ManagedCallbackBridge(vtkObject* caller, unsigned long eid, void* clientData, void*) {
    GCHandle handle = GCHandle::FromIntPtr(IntPtr(clientData));
    auto^ handler = safe_cast<VtkEventHandler^>(handle.Target);
    handler(VtkObjectManager::GetOrCreate<vtkObject^>(caller), eid);
}
```

### Маппинг типов

| C++ тип | C++/CLI managed тип |
|---------|-------------------|
| `int`, `double`, `float`, etc. | `int`, `double`, `float` (прямой) |
| `bool` | `bool` |
| `char*` / `std::string` | `System::String^` |
| `double*` (массив, известный размер) | `array<double>^` с `pin_ptr` + `memcpy` |
| `vtkObject*` | `VTK::vtkObject^` через `VtkObjectManager` |
| `enum` | C# `enum` (прямой маппинг) |
| `void (*callback)(...)` | `delegate` + `GCHandle` |

### Что должен делать генератор `vtkParseCSharpCLI.c`

Генератор потребляет `FileInfo*` от `vtkParse_Main()` и для каждого класса:

1. **Проверка wrappability**: `data->IsExcluded`, `vtkWrap_IsClassWrapped()`
2. **Определение суперкласса**: через `HierarchyInfo` (single inheritance)
3. **Генерация класса**: `public ref class vtkFoo : public vtkSuperClass`
4. **Для каждого public метода**:
   - Проверка: не excluded, не operator, не template
   - Классификация параметров через `vtkWrap_Is*` предикаты
   - Генерация managed-обёртки с конверсией типов
5. **Обнаружение Get/Set пар**: через `vtkParseProperties` → генерация C# properties
6. **Enum-ы**: прямой маппинг в C# `enum`

### Оценка объёма работы

| Компонент | Строк | Аналог |
|-----------|-------|--------|
| `vtkParseCSharpCLI.c` | ~1200 | `vtkParseJava.c` (1150) + `vtkWrapJava.c` (1600), но объединены |
| `CSharpCore/` (3-4 файла) | ~400 | `Wrapping/Java/vtk/*.java` (~500) |
| `vtkModuleWrapCSharp.cmake` | ~300 | `vtkModuleWrapJava.cmake` (520) |
| **Итого** | **~1900** | |

---

## 6. Альтернатива: P/Invoke (кроссплатформенный)

Если в будущем потребуется поддержка Linux/macOS, архитектура усложняется:

```
vtkFoo.h ──► vtkWrapCSharp.c   ──► vtkFooCSharp.cxx   (extern "C" exports)
         ──► vtkParseCSharp.c  ──► vtkFoo.cs            (managed class с [DllImport])
```

Два генератора + runtime на C# + `vtkCSharpUtil.cxx`. Итого ~4600 строк.

### Сравнение подходов

| Аспект | C++/CLI | P/Invoke |
|--------|---------|----------|
| Платформы | Windows only | Windows, Linux, macOS |
| Объём кода | ~1900 строк | ~4600 строк |
| Промежуточный C-слой | Не нужен | Нужен |
| Маршалинг | Автоматический | Ручной (`Marshal.Copy`, etc.) |
| Производительность | Максимальная (прямой вызов) | Overhead на P/Invoke transition |
| .NET совместимость | .NET Framework, .NET 5+ | Любой .NET |

---

## 7. Реализация (P/Invoke, кроссплатформенный подход)

Выбран **P/Invoke** подход для кроссплатформенности (Windows, Linux, macOS, .NET 8+).
Ветка: `feature/csharp-bindings`

### Созданные файлы

#### Генераторы кода (`Wrapping/Tools/`)
| Файл | Строк | Назначение |
|------|-------|------------|
| `vtkWrapCSharp.c` | ~850 | Генератор `extern "C"` экспортов для P/Invoke |
| `vtkParseCSharp.c` | ~900 | Генератор `.cs` файлов с `[DllImport]` |

#### C++ утилитный модуль (`Utilities/CSharp/`)
| Файл | Назначение |
|------|------------|
| `vtk.module` | Описание модуля VTK::CSharp |
| `CMakeLists.txt` | Сборка модуля |
| `vtkCSharpUtil.h` | Заголовок: экспорты для lifecycle и observer |
| `vtkCSharpUtil.cxx` | Реализация: Delete, Register, GetClassName, Print, AddObserver, RemoveObserver |

#### C# managed runtime (`Wrapping/CSharp/vtk/`)
| Файл | Строк | Назначение |
|------|-------|------------|
| `vtkObjectBase.cs` | ~110 | Базовый класс: IntPtr handle, IDisposable, GC-совместимость |
| `VtkObjectManager.cs` | ~120 | `ConcurrentDictionary` — один C++ объект = один C# wrapper |
| `VtkGarbageCollector.cs` | ~80 | Периодический sweep через `System.Threading.Timer` |
| `VtkReferenceInformation.cs` | ~100 | Статистика GC (per-class counters, debug mode) |
| `VtkNativeLibrary.cs.in` | ~80 | CMake-configured `NativeLibrary.SetDllImportResolver` |

#### CMake инфраструктура
| Файл | Назначение |
|------|------------|
| `CMake/vtkModuleWrapCSharp.cmake` | Главный модуль: запуск генераторов, сборка native библиотек |
| `CMake/vtkWrapSettings.cmake` | Опция `VTK_WRAP_CSHARP` |
| `CMakeLists.txt` (root) | Запрос VTK::CSharp + `add_subdirectory(Wrapping/CSharp)` |
| `Wrapping/CSharp/CMakeLists.txt` | Сборка `VTK.CSharp.dll` через `dotnet build` |
| `Wrapping/CSharp/VTK.CSharp.csproj.in` | Шаблон .csproj проекта |
| `Wrapping/Tools/CMakeLists.txt` | Регистрация WrapCSharp/ParseCSharp |

#### Тесты (`Wrapping/CSharp/Testing/`)
| Файл | Назначение |
|------|------------|
| `CSharpDelete.cs` | Explicit Dispose lifecycle |
| `CSharpGCAndDelete.cs` | Смешанный GC + Dispose |
| `CSharpConcurrencyGC.cs` | Многопоточный стресс-тест |
| `CSharpBindingCoverage.cs` | Рефлексия: все public классы имеют обёртки |
| `CMakeLists.txt` | Интеграция с `ctest` |

### Архитектура

```
vtkFoo.h ──► VTK::WrapCSharp  ──► vtkFooCSharp.cxx  (extern "C" exports)
         ──► VTK::ParseCSharp ──► vtkFoo.cs           (C# class with [DllImport])
```

Каждый VTK модуль производит:
- `${library_name}CSharp.so/.dll` — shared library с C экспортами
- `.cs` файлы, компилируемые в единую сборку `VTK.CSharp.dll`

### Сборка

```bash
cmake -DVTK_WRAP_CSHARP=ON ..
make                              # собирает native библиотеки
dotnet build VTK.CSharp.csproj    # собирает C# assembly
ctest -R vtkCSharpTests           # запускает тесты
```

### Следующие шаги

1. [ ] Скомпилировать и отладить на реальной VTK сборке
2. [ ] Проверить генерацию для `vtkCommonCore` модуля
3. [ ] Расширить на `vtkRenderingCore` и проверить рендеринг
4. [ ] Добавить NuGet-пакетирование
5. [ ] Добавить поддержку enum wrapping в генераторах
