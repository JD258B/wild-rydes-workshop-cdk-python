#!/usr/bin/env python3

from aws_cdk import core

from wild_rydes_cdk.wild_rydes_cdk_stack import WildRydesCdkStack


app = core.App()
WildRydesCdkStack(app, "wild-rydes-cdk")

app.synth()
