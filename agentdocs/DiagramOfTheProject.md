graph LR
    subgraph "External Data Sources"
        PM[Polymarket<br/>API]
        MMA[MMA<br/>API]
    end

    subgraph "High-Performance Backend (C++/Python)"
        CE[Central<br/>Engine]
        N[Normalize<br/>+ Validate]
        ES[(Event<br/>Store)]
        RAG[Agent / RAG<br/>Orchestrator]
    end

    subgraph "AI & Vector Layer"
        AI[AI<br/>Inference]
        VS[Vector<br/>Store]
    end

    subgraph "Frontend"
        UI[Dashboard]
    end

    PM -->|Market<br/>Events| CE
    MMA -->|Fight<br/>Stats| CE

    CE -->|Raw<br/>Events| N
    N -->|Canonical<br/>JSON| ES
    N -->|Canonical<br/>JSON| RAG

    RAG <-->|Model<br/>Inference| AI
    RAG <-->|Pattern<br/>Retrieval| VS

    CE -->|Streaming<br/>Updates| UI
    RAG -->|Prediction<br/>+ Evidence| UI
