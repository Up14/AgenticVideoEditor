from copy import deepcopy

def process_captions(input_json):
    captions = deepcopy(input_json["captions"])
    output = []

    i = 0
    n = len(captions)

    while i < n:
        curr = captions[i]

        # 1️⃣ First caption → push as-is
        if not output:
            output.append(curr)
            i += 1
            continue

        prev = output[-1]

        # 2️⃣ Case A: Exact duplicate
        if curr["text"] == prev["text"]:
            prev["end"] = curr["end"]
            i += 1
            continue

        # 3️⃣ Case B: Prefix extension
        if curr["text"].startswith(prev["text"]):
            remaining_text = curr["text"][len(prev["text"]):].strip()

            # If nothing new, just merge time
            if not remaining_text:
                prev["end"] = curr["end"]
                i += 1
                continue

            # Create temp caption for remaining text
            temp = {
                "start": curr["start"],
                "end": curr["end"],
                "text": remaining_text
            }

            # Look ahead to merge exact repeats of temp text
            j = i + 1
            while j < n and captions[j]["text"] == temp["text"]:
                temp["end"] = captions[j]["end"]
                j += 1

            output.append(temp)
            i = j
            continue

        # 4️⃣ Case C: Completely new caption
        output.append(curr)
        i += 1

    return {
        "source": input_json["source"],
        "language": input_json["language"],
        "caption_count": len(output),
        "captions": output
    }
