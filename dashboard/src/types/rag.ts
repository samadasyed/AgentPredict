/**
 * TypeScript mirrors of RagPrediction and EvidenceItem proto shapes.
 */

export interface EvidenceItem {
  text: string
  source_ref: string
  score: number  // Pinecone similarity [0, 1]
}

export interface RagPrediction {
  explanation: string
  evidence: EvidenceItem[]
  confidence: number        // [0, 1]
  timestamp: number         // unix millis
  trigger_event_id: string
}

/** Wrapper envelope from the gateway WebSocket. */
export interface PredictionMessage {
  type: 'prediction'
  data: RagPrediction
}
