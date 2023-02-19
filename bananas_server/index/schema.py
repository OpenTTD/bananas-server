from marshmallow import (
    fields,
    Schema,
    validate,
)
from marshmallow_enum import EnumField

from ..helpers.content_type import ContentType


class ContentEntry(Schema):
    class Meta:
        ordered = True

    content_id = fields.Integer(data_key="content-id")
    unique_id = fields.Raw(data_key="unique-id", validate=validate.Length(min=4, max=4))
    content_type = EnumField(ContentType, data_key="content-type", by_value=True)
    filesize = fields.Integer()
    # Most of these limits are limitations in the OpenTTD client.
    name = fields.String(validate=validate.Length(max=31))
    version = fields.String(validate=validate.Length(max=15))
    url = fields.String(validate=validate.Length(max=95))
    description = fields.String(validate=validate.Length(max=511))
    classification = fields.Dict(keys=fields.String(), values=fields.String())
    md5sum = fields.Raw(validate=validate.Length(min=16, max=16))
    compatibility = fields.Dict(
        keys=fields.String(),
        values=fields.Tuple(
            (
                fields.List(fields.Integer(), missing=None),
                fields.List(fields.Integer(), missing=None),
            )
        ),
    )
    raw_dependencies = fields.List(
        fields.Tuple(
            (
                EnumField(ContentType, by_value=True),
                fields.Raw(validate=validate.Length(min=4, max=4)),
                fields.Raw(validate=validate.Length(min=16, max=16)),
            )
        ),
        data_key="raw-dependencies",
    )
