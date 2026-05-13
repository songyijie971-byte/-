import unittest

from behavior_core import Detection, map_detections_to_behaviors


class BehaviorMappingTests(unittest.TestCase):
    def test_phone_labels_map_to_phone_behavior(self):
        labels = [
            "UsingPhone",
            "Phone",
            "phone",
            "playing phone",
            "mobile phone",
            "cell phone",
            "smartphone",
        ]

        detections = [
            Detection(index, label, 0.9, [0.0, 0.0, 10.0, 10.0], 1.0)
            for index, label in enumerate(labels)
        ]

        behaviors = map_detections_to_behaviors(detections)

        self.assertEqual(behaviors["phone"].count, len(labels))
        self.assertEqual(behaviors["phone"].source_class_ids, list(range(len(labels))))

    def test_hand_raise_label_variants_map_to_hand_raise(self):
        labels = [
            "HandRaise",
            "hand_raise",
            "hand-raise",
            "raise-hand",
            "RaiseHand",
            "raising-hand",
            "hand raising",
            "hand raise",
            "HandRaising",
            "hand-raising",
            "raise hand",
            "raising hand",
        ]

        detections = [
            Detection(index, label, 0.8, [0.0, 0.0, 10.0, 10.0], 1.0)
            for index, label in enumerate(labels)
        ]

        behaviors = map_detections_to_behaviors(detections)

        self.assertEqual(behaviors["hand_raise"].count, len(labels))
        self.assertEqual(behaviors["hand_raise"].source_class_ids, list(range(len(labels))))


if __name__ == "__main__":
    unittest.main()
