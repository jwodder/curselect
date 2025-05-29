# /// script
# dependencies = ["urwid ~= 2.1"]
# ///

"""
A library for presenting the user with a full-screen series of selection lists
(radio buttons or, for multi-selectables, checkboxes) and capturing their
selections

Outline of usage:
- Instantiate a `Form`
- Call `form.add(field, selector)` with each `Selector` or `MultiSelector` you
  wish to present the user
    - For those fields that can be set on both `Form` and the selector classes,
      leaving them unset/None on a selector causes the selector to inherit the
      value from the `Form`.
- Call `form.run()` to get the user's selections
    - Returns a `dict` mapping fields to the selections, or `None` if the user
      cancelled
    - The selection for a `Selector` is either the selected value or None
    - The selection for a `MultiSelector` is either a list of selected values
      or (if none were selected *and* the `defaults` parameter was `None`) None

Keybindings:
- j, DOWN — move down
- k, UP — move up
- h, LEFT — move left
- l, RIGHT — move right
- w, PAGE UP — go up a page
- z, PAGE DOWN — go down a page
- g — go to first item
- G — go to last item
- TAB — go to next list
- SHIFT+TAB — go to previous list
- ENTER, SPACE — select/activate current selection
- q, Q — cancel

TODO:
- Get multi-level focus changing with 'g', 'G', TAB, and SHIFT+TAB to work
  properly
    - <https://github.com/urwid/urwid/issues/466>
- Add a "required" option to the selector classes that causes "OK" to beep and
  not exit if nothing in the list is selected?
- Add `select()` and `multiselect()` functions for only showing a single
  selection list?
- Rename `[Multi]Selector` to `[Multi]Select`?
- Add options for setting the label-list gutter width?
- Add options for text to show at the top & bottom of the screen?
    - default top text: nothing
    - default bottom text: basic help
- Add help screen shown on '?'?
- Add option for custom help text?
"""

from __future__ import annotations
from collections.abc import Callable, Iterable, Iterator
from typing import TypeVar
import urwid

GUTTER = 2

REMAPPED_KEYS = {
    "j": "down",
    "k": "up",
    "h": "left",
    "l": "right",
    "w": "page up",
    "z": "page down",
}

K = TypeVar("K")
V = TypeVar("V")


class Form[K, V]:
    def __init__(
        self,
        *,
        display_func: Callable[[V], str] = str,
        left_margin: int = 8,
        label_on_top: bool = False,
    ) -> None:
        self.selectors: dict[K, Selector[V] | MultiSelector[V]] = {}
        self.selections: dict[K, V | list[V] | None] | None = None
        self.display_func = display_func
        self.left_margin = left_margin
        self.label_on_top = label_on_top

    def add(self, field: K, selector: Selector[V] | MultiSelector[V]) -> None:
        self.selectors[field] = selector

    def run(self) -> dict[K, V | list[V] | None] | None:
        self.selections = {
            field: selector._get_default() for field, selector in self.selectors.items()
        }
        widgets = []
        for field, selector in self.selectors.items():
            widgets.append(selector._mkwidget(self, field))
            widgets.append(urwid.Divider())
        widgets.append(self._ok_cancel())
        top = ListBoxTopBottable(urwid.SimpleListWalker(widgets))

        def _unhandler(key: str) -> None:
            # urwid doesn't seem to handle "ESC" as input well, so use 'q' to
            # cancel.
            if key == "q" or key == "Q":
                self._cancel(None)
            elif key == "g":
                top.focus_top()
            elif key == "G":
                top.focus_bottom()
            elif key == "tab":
                top.focus_next()
            elif key == "shift tab":
                top.focus_prev()

        urwid.MainLoop(
            top,
            input_filter=remap_keys,
            unhandled_input=_unhandler,
        ).run()
        return self.selections

    def _ok_cancel(self) -> urwid.Columns:
        # return urwid.GridFlow(
        #    [
        #        urwid.Button("OK", on_press=self._exit),
        #        urwid.Button("Cancel", on_press=self._cancel),
        #    ],
        #    cell_width=10,
        #    h_sep=2,
        #    v_sep=0,
        #    align='center',
        # )
        return urwid.Columns(
            [
                ("weight", 1, urwid.Text("")),
                (10, urwid.Button("OK", on_press=self._exit)),
                ("weight", 1, urwid.Text("")),
                (10, urwid.Button("Cancel", on_press=self._cancel)),
                ("weight", 1, urwid.Text("")),
            ],
            dividechars=2,
        )

    def _set_selection(
        self, _button: urwid.RadioButton, state: bool, user_data: tuple[K, V]
    ) -> None:
        field, value = user_data
        if state:
            assert self.selections is not None
            self.selections[field] = value

    def _set_multiselection(
        self, _button: urwid.CheckBox, state: bool, user_data: tuple[K, V]
    ) -> None:
        field, value = user_data
        assert self.selections is not None
        selected = self.selections[field]
        assert isinstance(selected, list)
        if state:
            selected.append(value)
        else:
            selected.remove(value)

    def _cancel(self, button: urwid.Button) -> None:
        self.selections = None
        self._exit(button)

    def _exit(self, _button: urwid.Button) -> None:
        raise urwid.ExitMainLoop()


class Selector[V]:
    def __init__(
        self,
        label: str,
        options: Iterable[V],
        *,
        display_func: Callable[[V], str] | None = None,
        left_margin: int | None = None,
        label_on_top: bool | None = None,
        default: int | None = None,
    ):
        self.label: str = label
        self.options = list(options)
        self.display_func = display_func
        self.left_margin = left_margin
        self.label_on_top = label_on_top
        self.default = default

    def _get_default(self) -> V | None:
        if self.default is None:
            return None
        else:
            return self.options[self.default]

    def _mkwidget(self, form: Form[K, V], field: K) -> urwid.Widget:
        label_widget = urwid.Text(self.label)
        left_margin = none_or(self.left_margin, form.left_margin)
        w, _ = label_widget.pack()
        if w > left_margin - GUTTER:
            label_on_top = True
        else:
            label_on_top = none_or(self.label_on_top, form.label_on_top)
        display_func = none_or(self.display_func, form.display_func)
        buttons: list[urwid.RadioButton] = []
        button_pile = PileTopBottable(
            [
                urwid.RadioButton(
                    buttons,
                    display_func(opt),
                    state=i == self.default,
                    on_state_change=form._set_selection,
                    user_data=(field, opt),
                )
                for i, opt in enumerate(self.options)
            ]
        )
        if label_on_top:
            return PileTopBottable(
                [
                    label_widget,
                    urwid.Padding(button_pile, left=left_margin),
                ]
            )
        else:
            return ColumnsTopBottable(
                [
                    (left_margin - GUTTER, label_widget),
                    button_pile,
                ],
                dividechars=GUTTER,
                focus_column=1,
            )


class MultiSelector[V]:
    def __init__(
        self,
        label: str,
        options: Iterable[V],
        *,
        display_func: Callable[[V], str] | None = None,
        left_margin: int | None = None,
        label_on_top: bool | None = None,
        defaults: Iterator[int] | None = None,
    ):
        self.label = label
        self.options = list(options)
        self.display_func = display_func
        self.left_margin = left_margin
        self.label_on_top = label_on_top
        if defaults is not None:
            self.defaults = list(defaults)
        else:
            self.defaults = []

    def _get_default(self) -> list[V] | None:
        if not self.defaults:
            return None
        else:
            return [self.options[i] for i in self.defaults]

    def _mkwidget(self, form: Form[K, V], field: K) -> urwid.Widget:
        label_widget = urwid.Text(self.label)
        left_margin = none_or(self.left_margin, form.left_margin)
        w, _ = label_widget.pack()
        if w > left_margin - GUTTER:
            label_on_top = True
        else:
            label_on_top = none_or(self.label_on_top, form.label_on_top)
        display_func = none_or(self.display_func, form.display_func)
        button_pile = urwid.Pile(
            [
                urwid.CheckBox(
                    display_func(opt),
                    state=i in self.defaults,
                    on_state_change=form._set_multiselection,
                    user_data=(field, opt),
                )
                for i, opt in enumerate(self.options)
            ]
        )
        if label_on_top:
            return urwid.Pile(
                [
                    label_widget,
                    urwid.Padding(button_pile, left=left_margin),
                ]
            )
        else:
            return urwid.Columns(
                [
                    (left_margin - GUTTER, label_widget),
                    button_pile,
                ],
                dividechars=GUTTER,
                focus_column=1,
            )


class TopBottable:
    def get_elements(self) -> list[urwid.Widget]:
        raise NotImplementedError

    def focus_top(self) -> None:
        for i, w in enumerate(self.get_elements()):
            if w.selectable():
                self.focus_position = i
                if hasattr(w, "focus_top"):
                    w.focus_top()
                return

    def focus_bottom(self) -> None:
        elements = self.get_elements()
        for i in range(len(elements) - 1, -1, -1):
            w = elements[i]
            if w.selectable():
                self.focus_position = i
                if hasattr(w, "focus_bottom"):
                    w.focus_bottom()
                return


class ListBoxTopBottable(urwid.ListBox, TopBottable):
    def get_elements(self) -> list[urwid.Widget]:
        return list(self.body)

    def focus_next(self) -> None:
        indices = list(range(len(self.body)))
        indices = (
            indices[self.focus_position + 1 :] + indices[: self.focus_position + 1]
        )
        for i in indices:
            w = self.body[i]
            if w.selectable():
                self.focus_position = i
                if hasattr(w, "focus_top"):
                    w.focus_top()
                return

    def focus_prev(self) -> None:
        indices = list(range(len(self.body)))
        indices = indices[self.focus_position :] + indices[: self.focus_position]
        indices.reverse()
        for i in indices:
            w = self.body[i]
            if w.selectable():
                self.focus_position = i
                if hasattr(w, "focus_top"):
                    w.focus_top()
                return


class PileTopBottable(urwid.Pile, TopBottable):
    def get_elements(self) -> list[urwid.Widget]:
        return [w for w, _ in self.contents]


class ColumnsTopBottable(urwid.Columns, TopBottable):
    def get_elements(self) -> list[urwid.Widget]:
        return [w for w, _ in self.contents]


def none_or(a: K | None, b: K) -> K:
    return a if a is not None else b


def remap_keys(keys: Iterable[str], _raw: list[int]) -> list[str]:
    return [REMAPPED_KEYS.get(k, k) for k in keys]
