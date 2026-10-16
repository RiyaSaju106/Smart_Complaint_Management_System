"""Processing & Status module.
 
    from <this folder> import processing_bp
    app.register_blueprint(processing_bp)
"""
from .routes import processing_bp
 
__all__ = ["processing_bp"]
