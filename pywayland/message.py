# Copyright 2015 Sean Vig
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pywayland import ffi, lib

import re
import weakref

weakkeydict = weakref.WeakKeyDictionary()

re_arg = re.compile(r"(\??)([uifsonah])")


class Message(object):
    """Wrapper class for `wl_message` structs

    Base class that correspond to the methods defined on an interface in the
    wayland.xml protocol, and are generated by the scanner.  Subclasses specify
    the type of method, whether it is a server-side or client-side method.

    :param func: The function that is represented by the message
    :type func: `function`
    :param signature: The signature of the arguments of the message
    :type signature: `string`
    :param types:  List of the types of any objects included in the argument
                   list, None if otherwise.
    :type types: `list`
    """
    def __init__(self, func, signature, types):
        self._func = func
        self.name = func.__name__.strip('_')
        self.signature = signature
        self.types = types

        self._ptr = ffi.new('struct wl_message *')
        self._ptr.name = name = ffi.new('char[]', self.name.encode())
        self._ptr.signature = signature = ffi.new('char[]', self.signature.encode())

        self._ptr.types = types = ffi.new('struct wl_interface* []', len(self.types))
        for i, _type in enumerate(self.types):
            if _type:
                self._ptr.types[i] = _type._ptr
            else:
                self._ptr.types[i] = ffi.NULL

        weakkeydict[self._ptr] = (name, signature, types)

    def c_to_arguments(self, args_ptr):
        """Create a list of arguments

        Generate the arguments of the method from a CFFI cdata array of
        `wl_argument` structs that correspond to the arguments of the method as
        specified by the method signature.

        :param args_ptr: Input arguments
        :type args_ptr: cdata `union wl_argument []`
        :returns: list of args
        """
        args = []
        for i, sig_match in enumerate(re_arg.finditer(self.signature)):
            arg_ptr = args_ptr[i]
            null, sig = sig_match.groups()

            # Match numbers (int, unsigned, float, file descriptor)
            if sig == 'i':
                args.append(arg_ptr.i)
            elif sig == 'u':
                args.append(arg_ptr.u)
            elif sig == 'f':
                f = lib.wl_fixed_to_double(arg_ptr.f)
                args.append(f)
            elif sig == 'h':
                args.append(arg_ptr.h)
            # Match string
            elif sig == 's':
                if arg_ptr == ffi.NULL:
                    if not null:
                        raise Exception
                    args.append(None)
                else:
                    args.append(ffi.string(arg_ptr.s).decode())
            # Object or new id
            elif sig in ('o', 'n'):
                # TODO
                pass
            # Array (i.e. buffer of bytes)
            elif sig == 'a':
                # TODO
                pass

        return args

    def arguments_to_c(self, *args):
        """Create an array of `wl_argument` C structs

        Generate the CFFI cdata array of `wl_argument` structs that correspond
        to the arguments of the method as specified by the method signature.

        :param args: Input arguments
        :type args: `list`
        :returns: cdata `union wl_argument []` of args
        """
        nargs = len(re_arg.findall(self.signature))
        args_ptr = ffi.new('union wl_argument []', nargs)

        arg_iter = iter(args)
        refs = []
        for i, sig_match in enumerate(re_arg.finditer(self.signature)):
            null, sig = sig_match.groups()

            # New id (set to null for now, will be assigned on marshal)
            # Then, continue so we don't consume an arg
            if sig == 'n':
                args_ptr[i].o = ffi.NULL
                continue
            arg = next(arg_iter)
            # Match numbers (int, unsigned, float, file descriptor)
            if sig == 'i':
                args_ptr[i].i = arg
            elif sig == 'u':
                args_ptr[i].u = arg
            elif sig == 'f':
                if isinstance(arg, int):
                    f = lib.wl_fixed_from_int(arg)
                else:
                    f = lib.wl_fixed_from_double(arg)
                args_ptr[i].f = f
            elif sig == 'h':
                args_ptr[i].h = arg
            # Match string
            elif sig == 's':
                if arg is None:
                    if not null:
                        raise Exception
                    new_arg = ffi.NULL
                else:
                    new_arg = ffi.new('char []', arg.encode())
                    refs.append(new_arg)
                args_ptr[i].s = new_arg
            # Object
            elif sig == 'o':
                if arg is None:
                    if not null:
                        raise Exception
                    new_arg = ffi.NULL
                else:
                    new_arg = ffi.cast('struct wl_object *', arg._ptr)
                    refs.append(new_arg)
                args_ptr[i].o = new_arg
            # Array (i.e. buffer of bytes)
            elif sig == 'a':
                new_arg = ffi.new('struct wl_array *')
                new_data = ffi.new('void []', len(arg))
                new_arg.alloc = new_arg.size = len(arg)
                ffi.buffer(new_data)[:] = arg
                refs.append(new_arg)
                refs.append(new_data)

        if refs:
            weakkeydict[args_ptr] = refs

        return args_ptr
