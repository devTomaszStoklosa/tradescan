"""Request and response models of the HTTP API, one module per module of `routes`; shared pieces in
`common`.

Floats that are NaN or infinite in pandas are sent as `null`, because JSON cannot represent them.
"""
