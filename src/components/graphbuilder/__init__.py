"""Graph builder package — pure construction of Graph objects from MedicalDocument.

No persistence logic lives here. Use GraphBuilderFactory to create builders,
or import directly:

    from src.components.graphbuilder import GraphifyyBuilder
    graph = GraphifyyBuilder(config).build_from_documents(documents)
"""
