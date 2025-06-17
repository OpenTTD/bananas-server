from marshmallow import (
    fields,
    Schema,
    validate,
)

from ..helpers.content_type import ContentType


class ContentEntry(Schema):
    class Meta:
        ordered = True

    content_id = fields.Integer(data_key="content-id")
    unique_id = fields.Raw(data_key="unique-id", validate=validate.Length(min=4, max=4))
    content_type = fields.Enum(ContentType, data_key="content-type", by_value=True)
    filesize = fields.Integer()
    # Most of these limits are limitations in the OpenTTD client.
    name = fields.String(validate=validate.Length(max=31))
    version = fields.String(validate=validate.Length(max=15))
    url = fields.String(validate=validate.Length(max=95))
    description = fields.String(validate=validate.Length(max=511))
    regions = fields.List(fields.String(), validate=validate.Length(max=10))
    classification = fields.Dict(keys=fields.String(), values=fields.String())
    md5sum = fields.Raw(validate=validate.Length(min=16, max=16))
    compatibility = fields.Dict(
        keys=fields.String(),
        values=fields.Tuple(
            (
                fields.List(fields.Integer(), load_default=None),
                fields.List(fields.Integer(), load_default=None),
            )
        ),
    )
    raw_dependencies = fields.List(
        fields.Tuple(
            (
                fields.Enum(ContentType, by_value=True),
                fields.Raw(validate=validate.Length(min=4, max=4)),
                fields.Raw(validate=validate.Length(min=16, max=16)),
            )
        ),
        data_key="raw-dependencies",
    )
