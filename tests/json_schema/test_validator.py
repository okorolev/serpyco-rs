import json
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Literal, Optional, Union, Callable
from unittest import mock

import pytest
from serpyco_rs import Serializer
from serpyco_rs._describe import describe_type
from serpyco_rs._json_schema import get_json_schema
from serpyco_rs.exceptions import ErrorItem, SchemaValidationError, ValidationError
from serpyco_rs.metadata import Discriminator, Max, MaxLength, Min, MinLength
from typing_extensions import NotRequired, Required, TypedDict


class EnumTest(Enum):
    foo = 'foo'
    bar = 'bar'


@dataclass
class EntityTest:
    key: str


@dataclass
class Foo:
    type: Literal['foo']
    val: int


@dataclass
class Bar:
    type: Literal['bar']
    val: str


class TypedDictTotalTrue(TypedDict):
    foo: int
    bar: NotRequired[str]


class TypedDictTotalFalse(TypedDict, total=False):
    foo: int
    bar: Required[str]


@pytest.mark.parametrize(
    ['cls', 'value'],
    (
        (bool, True),
        (bool, False),
        (str, ''),
        (Annotated[str, MinLength(1), MaxLength(3)], '12'),
        (int, -99),
        (Annotated[int, Min(1), Max(1000)], 99),
        # (bytes, b'xx'),  # todo: fix bytes validation
        (float, 1.3),
        (Annotated[float, Min(0), Max(0.4)], 0.1),
        (Decimal, '0.1'),  # support str
        (Decimal, 0.1),  # or int input
        (Decimal, 'NaN'),  # or int input
        (uuid.UUID, str(uuid.uuid4())),  # support only str input
        (time, '12:34'),
        (time, '12:34:56'),
        (time, '12:34:56.000078'),
        (time, '12:34Z'),
        (time, '12:34+0300'),
        (time, '12:34+03:00'),
        (time, '12:34:00+03:00'),
        (time, '12:34:56.000078+03:00'),
        (time, '12:34:56.000078+00:00'),
        # todo: add datetime exemplars
        (datetime, '2022-10-10T14:23:43'),
        (datetime, '2022-10-10T14:23:43.123456'),
        (datetime, '2022-10-10T14:23:43.123456Z'),
        (datetime, '2022-10-10T14:23:43.123456+00:00'),
        # (datetime, '2022-10-10T14:23:43.123456-30:00'),  # todo: check
        (date, '2020-07-17'),
        (EnumTest, 'foo'),
        (Optional[int], None),
        (Optional[int], 1),
        (EntityTest, {'key': 'val'}),
        (list[int], [1, 2]),
        (dict[str, int], {'a': 1}),
        (tuple[str, int, bool], ['1', 2, True]),
        (Annotated[Union[Foo, Bar], Discriminator('type')], {'type': 'foo', 'val': 1}),
        (Annotated[Union[Foo, Bar], Discriminator('type')], {'type': 'bar', 'val': '1'}),
        (Any, ['1', 2, True]),
        (Any, {}),
        (TypedDictTotalTrue, {'foo': 1}),
        (TypedDictTotalTrue, {'foo': 1, 'bar': '1'}),
        (TypedDictTotalFalse, {'bar': '1'}),
        (TypedDictTotalFalse, {'foo': 1, 'bar': '1'}),
    ),
)
def test_validate(cls, value):
    Serializer(cls).load(value)


if sys.version_info >= (3, 10):

    @pytest.mark.parametrize(
        ['cls', 'value'],
        (
            (Optional[int], None),
            (int | None, None),
            (int | None, 2),
        ),
    )
    def test_validate_new_union(cls, value):
        Serializer(cls).load(value)


def _mk_e(m=mock.ANY, ip=mock.ANY, sp=mock.ANY) -> Callable[[ErrorItem], bool]:
    def cmp(e: ErrorItem) -> bool:
        return e.message == m and e.instance_path == ip and e.schema_path == sp

    return cmp


@pytest.mark.parametrize(
    ['cls', 'value', 'comparator'],
    (
        (bool, 1, _mk_e(m='1 is not of type "boolean"')),
        (str, 1, _mk_e(m='1 is not of type "string"')),
        (
            Annotated[str, MinLength(2)],
            'a',
            _mk_e(m='"a" is shorter than 2 characters', sp='minLength'),
        ),
        (
            Annotated[str, MaxLength(2)],
            'aaa',
            _mk_e(m='"aaa" is longer than 2 characters', sp='maxLength'),
        ),
        (int, 9.1, _mk_e(m='9.1 is not of type "integer"')),
        (int, '9', _mk_e(m='"9" is not of type "integer"')),
        (
            Annotated[int, Min(1)],
            0,
            _mk_e(m='0 is less than the minimum of 1', sp='minimum'),
        ),
        (
            Annotated[int, Max(1)],
            10,
            _mk_e(m='10 is greater than the maximum of 1', sp='maximum'),
        ),
        (float, None, _mk_e(m='null is not of type "number"')),
        (
            Annotated[float, Min(1)],
            0.1,
            _mk_e(m='0.1 is less than the minimum of 1', sp='minimum'),
        ),
        (
            Annotated[float, Max(1)],
            10.1,
            _mk_e(m='10.1 is greater than the maximum of 1', sp='maximum'),
        ),
        # (uuid.UUID, "asd", ''),  # todo: validation don't work
        (time, '12:34:a', _mk_e(sp='pattern')),
        (datetime, '2022-10-10//12', _mk_e(sp='pattern')),
        (date, '17-02-2022', _mk_e(sp='pattern')),
        (EnumTest, 'buz', _mk_e(m='"buz" is not one of ["foo","bar"]', sp='enum')),
        (
            Optional[int],
            'foo',
            _mk_e(m='"foo" is not valid under any of the schemas listed in the \'anyOf\' keyword', sp='anyOf'),
        ),
        (EntityTest, {}, _mk_e(m='"key" is a required property', sp='required')),
        (
            list[int],
            [1, '1'],
            _mk_e(m='"1" is not of type "integer"', ip='1', sp='items/type'),
        ),
        (
            dict[str, int],
            {'a': '1'},
            _mk_e(m='"1" is not of type "integer"', ip='a', sp='additionalProperties/type'),
        ),
        (
            tuple[str, int, bool],
            ['1'],
            _mk_e(m='["1"] has less than 3 items', sp='minItems'),
        ),
        (
            tuple[str, int, bool],
            ['1', 1, True, 0],
            _mk_e(m='["1",1,true,0] has more than 3 items', sp='maxItems'),
        ),
        # (tuple[str, bool], [1, '1'], ''),   # todo: validation don't work
        (
            Annotated[Union[Foo, Bar], Discriminator('type')],
            {'type': 'buz'},
            _mk_e(m='{"type":"buz"} is not valid under any of the schemas listed in the \'oneOf\' keyword', sp='oneOf'),
        ),
        (
            Annotated[Union[Foo, Bar], Discriminator('type')],
            {'type': 'foo', 'val': '123'},
            _mk_e(sp='oneOf'),
        ),
        (
            Annotated[Union[Foo, Bar], Discriminator('type')],
            {'type': 'bar', 'val': 1},
            _mk_e(sp='oneOf'),
        ),
        (TypedDictTotalTrue, {}, _mk_e(m='"foo" is a required property')),
        (TypedDictTotalFalse, {}, _mk_e(m='"bar" is a required property')),
    ),
)
def test_validate__validation_error(cls, value, comparator):
    serializer = Serializer(cls)
    raw_value = json.dumps(value)
    with pytest.raises(SchemaValidationError) as exc_info:
        serializer.load(value)

    with pytest.raises(SchemaValidationError) as raw_exc_info:
        serializer.load_json(raw_value)

    assert len(exc_info.value.errors) == 1
    assert comparator(exc_info.value.errors[0])
    assert exc_info.value.errors == raw_exc_info.value.errors


def test_validate__error_format():
    @dataclass
    class Inner:
        baz: str

    @dataclass
    class A:
        foo: int
        bar: Inner

    serializer = Serializer(A)

    value = {'foo': '1', 'bar': {'buz': None}, 'qux': 0}

    with pytest.raises(SchemaValidationError) as exc_info:
        serializer.load(value)

    with pytest.raises(SchemaValidationError) as raw_exc_info:
        serializer.load_json(json.dumps(value))

    assert (
        exc_info.value.errors
        == raw_exc_info.value.errors
        == [
            ErrorItem(
                message='"baz" is a required property',
                instance_path='bar',
                schema_path='required',
            ),
            ErrorItem(
                message='"1" is not of type "integer"',
                instance_path='foo',
                schema_path='properties/foo/type',
            ),
        ]
    )


def test_validation_exceptions_inheritance():
    serializer = Serializer(int)
    with pytest.raises(SchemaValidationError) as exc_info:
        serializer.load('1')

    assert isinstance(exc_info.value, ValidationError)
    assert exc_info.value.message == 'Validation failed'
