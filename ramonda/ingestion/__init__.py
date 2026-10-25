def ingest():
    from . import chunk, enrich, parse_docling, parse_tika, parse_unstructured

    parse_tika.main()
    parse_unstructured.main()
    parse_docling.main()
    chunk.main()
    enrich.main()
