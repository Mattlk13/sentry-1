import pytest

from sentry.interfaces.stacktrace import Frame
from sentry.stacktraces.functions import (
    get_source_link_for_frame,
    replace_enclosed_string,
    split_func_tokens,
    trim_function_name,
)


@pytest.mark.parametrize(
    "input,output",
    [
        [
            "Scaleform::GFx::AS3::IMEManager::DispatchEvent(char const *,char const *,char const *)",
            "Scaleform::GFx::AS3::IMEManager::DispatchEvent",
        ],
        [
            "static unsigned int Scaleform::GFx::AS3::IMEManager::DispatchEvent(char const *,char const *,char const *) const",
            "Scaleform::GFx::AS3::IMEManager::DispatchEvent",
        ],
        [
            "Scaleform::GFx::IME::GImeNamesManagerVista::OnActivated(unsigned long,unsigned short,_GUID const &,_GUID const &,_GUID const &,HKL__ *,unsigned long)",
            "Scaleform::GFx::IME::GImeNamesManagerVista::OnActivated",
        ],
        [
            "<actix_web::pipeline::Pipeline<S, H> as actix_web::server::handler::HttpHandlerTask>::poll_io",
            "actix_web::pipeline::Pipeline<T>::poll_io",
        ],
        ["+[FLFoo barBaz]", "+[FLFoo barBaz]"],
        ["-[FLFoo barBaz]", "-[FLFoo barBaz]"],
        [
            "<tokio_current_thread::scheduler::Scheduled<'a, U>>::tick",
            "tokio_current_thread::scheduler::Scheduled<T>::tick",
        ],
        [
            "tokio::runtime::current_thread::runtime::Runtime::enter::{{closure}}::{{closure}}::{{closure}}::{{closure}}",
            "tokio::runtime::current_thread::runtime::Runtime::enter::{{closure}}::{{closure}}::{{closure}}::{{closure}}",
        ],
        [
            "<std::panic::AssertUnwindSafe<F> as core::ops::function::FnOnce<()>>::call_once",
            "std::panic::AssertUnwindSafe<T>::call_once",
        ],
        [
            "struct style::gecko_bindings::sugar::ownership::Strong<style::gecko_bindings::structs::root::RawServoStyleSheetContents> geckoservo::glue::Servo_StyleSheet_Empty(style::gecko_bindings::structs::root::mozilla::css::SheetParsingMode) const",
            "geckoservo::glue::Servo_StyleSheet_Empty",
        ],
        [
            "static <NoType> std::panicking::begin_panic<str*>(struct str*, struct (str*, u32, u32) *)",
            "std::panicking::begin_panic<T>",
        ],
        [
            "(anonymous namespace)::StupidFunction<std::vector<std::string>>(int)",
            "(anonymous namespace)::StupidFunction<T>",
        ],
        ["static unsigned int _foo_function (uint32_t,uint32_t) const", "_foo_function"],
        [
            "v8::internal::operator<<(std::__1::basic_ostream<char, std::__1::char_traits<char> >&, v8::internal::MaybeObjectBrief const&)",
            "v8::internal::operator<<",
        ],
        [
            "unsigned int (anonymous namespace)::operator<<(std::__1::basic_ostream<char, std::__1::char_traits<char> >&, v8::internal::MaybeObjectBrief const&)",
            "(anonymous namespace)::operator<<",
        ],
        [
            "unsigned int mynamespace::MyClass::operator()(std::__1::basic_ostream<char, std::__1::char_traits<char> >&, v8::internal::MaybeObjectBrief const&)",
            "mynamespace::MyClass::operator()",
        ],
        [
            "std::basic_ostream<char, std::char_traits<char> >& std::operator<< <std::char_traits<char> >(std::basic_ostream<char, std::char_traits<char> >&, char)",
            "std::operator<< <T>",
        ],
        [
            "<actix::contextimpl::ContextFut<A, C> as futures::future::Future>::poll::h9de5fbebc1652d47",
            "actix::contextimpl::ContextFut<T>::poll",
        ],
        ["<T as core::convert::Into<U>>::into", "core::convert::Into<T>::into"],
        ["ThreadStartWhatever@16", "ThreadStartWhatever"],
        ["@ThreadStartWhatever@16", "ThreadStartWhatever"],
        ["@objc ViewController.causeCrash(Any) -> ()", "ViewController.causeCrash"],
        ["ViewController.causeCrash(Any) -> ()", "ViewController.causeCrash"],
        [
            "@objc ViewController.causeCrash(Any, Foo -> Bar) -> SomeObject",
            "ViewController.causeCrash",
        ],
        ["ViewController.causeCrash(Any) -> SomeObject", "ViewController.causeCrash"],
        ["main::$_0", "main::lambda"],
        ["main::$_42", "main::lambda"],
        ["main::{lambda(int)#1}", "main::lambda"],
        ["main::{lambda()#42}", "main::lambda"],
        ["lambda_7156c3ceaa11256748687ab67e3ef4cd", "lambda"],
        ["<lambda_7156c3ceaa11256748687ab67e3ef4cd>::operator()", "<lambda>::operator()"],
        ["trigger_crash_a(int*) [clone .constprop.0]", "trigger_crash_a"],
        ["ShellCorona::screenInvariants() const [clone .cold]", "ShellCorona::screenInvariants"],
        [
            "__gnu_cxx::__verbose_terminate_handler() [clone .cold]",
            "__gnu_cxx::__verbose_terminate_handler",
        ],
        [
            "std::__1::unique_ptr<X,std::default_delete<X> >::operator->",
            "std::__1::unique_ptr<T>::operator->",
        ],
        ["pthread_cond_timedwait@@GLIBC_2.3.2", "pthread_cond_timedwait"],
        ["glob64@GLIBC_2.2", "glob64"],
        [
            "static Namespace.ThrowingFunction() throws -> Namespace.ExitValue?",
            "Namespace.ThrowingFunction",
        ],
        [
            "closure #1 @Swift.MainActor () -> () in static Foo.CallFunction(args: [Swift.String]) -> ()",
            "closure in Foo.CallFunction",
        ],
        [
            "closure #1 () -> () in Bar.PostTask(() -> ()) -> ()",
            "closure in Bar.PostTask",
        ],
        [
            "closure #1 @Sendable () -> Swift.String in variable initialization expression of static Namespace.Class.var : Namespace.Parent",
            "closure in initializer expression of Namespace.Class.var",
        ],
        [
            "variable initialization expression of static Namespace.Class.var : Namespace.Parent",
            "initializer expression of Namespace.Class.var",
        ],
        [
            "closure #1 () -> () in variable initialization expression of static (extension in SpaceCreation):Namespace.Class.var : Namespace.Parent",
            "closure in initializer expression of Namespace.Class.var",
        ],
    ],
)
def test_trim_native_function_name(input, output) -> None:
    assert trim_function_name(input, "native") == output


@pytest.mark.parametrize(
    "input,output",
    [
        ["UnityEngine.Events.InvokableCall.Invoke ()", "UnityEngine.Events.InvokableCall.Invoke"],
        [
            "UnityEngine.EventSystems.ExecuteEvents.Execute[T] (UnityEngine.GameObject target, UnityEngine.EventSystems.BaseEventData eventData, UnityEngine.EventSystems.ExecuteEvents+EventFunction`1[T1] functor)",
            "UnityEngine.EventSystems.ExecuteEvents.Execute[T]",
        ],
    ],
)
def test_trim_csharp_function_name(input, output) -> None:
    assert trim_function_name(input, "csharp") == output


@pytest.mark.parametrize(
    "input,output",
    [
        [
            "thunk for @escaping @callee_guaranteed () -> ()",
            "thunk for closure",
        ],
        [
            "specialized thunk for @callee_guaranteed (@guaranteed [T1]) -> (@owned [T2])",
            "thunk for closure",
        ],
        [
            "partial apply for thunk for @callee_guaranteed () -> (@error @owned Error)",
            "thunk for closure",
        ],
        [
            "partial apply for thunk for @escaping @callee_guaranteed (@guaranteed SomeType, @guaranteed [String : SomeType2], @guaranteed SomeType3) -> ()",
            "thunk for closure",
        ],
        [
            "closure #1 (T1) in foo(bar: T2)",
            "closure in foo",
        ],
        [
            "partial apply for closure #1 () in closure #2 (T1) in f1(_: T2, arg: T3)",
            "closure in f1",
        ],
    ],
)
def test_trim_cocoa_function_name(input, output) -> None:
    assert trim_function_name(input, "cocoa") == output


def replace_group(value, start):
    if start == 0:
        assert value == "anonymous namespace"
        return "(new value)"
    return "()"


@pytest.mark.parametrize(
    "input,start,end,replacement,output",
    [
        ["foo::bar<Blah, Blah<Blah, Blah>>", "<", ">", "<T>", "foo::bar<T>"],
        ["foo::bar(unsigned int, int)", "(", ")", "", "foo::bar"],
        [
            "(anonymous namespace)::foo::bar(unsigned int, int)",
            "(",
            ")",
            replace_group,
            "(new value)::foo::bar()",
        ],
    ],
)
def test_enclosed_string_simple(input, start, end, replacement, output) -> None:
    assert replace_enclosed_string(input, start, end, replacement) == output


@pytest.mark.parametrize(
    "input,output",
    [
        ["foo bar baz", ["foo", "bar", "baz"]],
        ["foo bar (enclosed baz)", ["foo", "bar", "(enclosed baz)"]],
        ["foo (enclosed bar) baz", ["foo", "(enclosed bar)", "baz"]],
        ["foo(enclosed bar)baz {moar stuff}", ["foo(enclosed bar)baz", "{moar stuff}"]],
        ["foo bar [baz (blah)]", ["foo", "bar", "[baz (blah)]"]],
    ],
)
def test_split_func_tokens(input, output) -> None:
    assert split_func_tokens(input) == output


def test_trim_function_name_cocoa() -> None:
    assert trim_function_name("+[foo:(bar)]", "objc") == "+[foo:(bar)]"
    assert trim_function_name("[foo:(bar)]", "objc") == "[foo:(bar)]"
    assert trim_function_name("-[foo:(bar)]", "objc") == "-[foo:(bar)]"
    assert (
        trim_function_name("(anonymous namespace)::foo(int)", "native")
        == "(anonymous namespace)::foo"
    )
    assert trim_function_name("foo::bar::foo(int)", "native") == "foo::bar::foo"


@pytest.mark.parametrize(
    "input,output",
    [
        [
            {
                "source_link": "https://raw.githubusercontent.com/author/repo/abc123456789/foo/bar/baz.js",
                "lineno": "200",
            },
            "https://www.github.com/author/repo/blob/abc123456789/foo/bar/baz.js#L200",
        ],
        [
            {
                "source_link": "https://raw.githubusercontent.com/author/repo/abc123456789/foo/bar/baz.js"
            },
            "https://www.github.com/author/repo/blob/abc123456789/foo/bar/baz.js",
        ],
        [
            {"source_link": "https://raw.githubusercontent.com/author/repo"},
            "https://raw.githubusercontent.com/author/repo",
        ],
        [
            {
                "source_link": "https://notraw.githubusercontent.com/notauthor/notrepo/notfile/foo/bar/baz.js",
                "lineno": "122",
            },
            "https://notraw.githubusercontent.com/notauthor/notrepo/notfile/foo/bar/baz.js",
        ],
        [{"lineno": "543"}, None],
        [{"source_link": "woejfdsiwjidsoi", "lineNo": "7"}, None],
    ],
)
def test_get_source_link_for_frame(input, output) -> None:
    assert get_source_link_for_frame(Frame.to_python(input)) == output
