<AutoPilot:project xmlns:AutoPilot="com.autoesl.autopilot.project" projectType="C/C++" name="compare_hls" ideType="classic" top="image_preprocess">
    <files>
        <file name="image_preprocess.h" sc="0" tb="false" cflags="" csimflags="" blackbox="false"/>
        <file name="image_preprocess.cpp" sc="0" tb="false" cflags="" csimflags="" blackbox="false"/>
        <file name="../../test_vectors/expected_1.txt" sc="0" tb="1" cflags="-Wno-unknown-pragmas" csimflags="" blackbox="false"/>
        <file name="../../test_vectors/expected_0.txt" sc="0" tb="1" cflags="-Wno-unknown-pragmas" csimflags="" blackbox="false"/>
        <file name="../../test_vectors/input_rgb.txt" sc="0" tb="1" cflags="-Wno-unknown-pragmas" csimflags="" blackbox="false"/>
        <file name="../../tb_compare.cpp" sc="0" tb="1" cflags="-Wno-unknown-pragmas" csimflags="" blackbox="false"/>
    </files>
    <Simulation argv="">
        <SimFlow name="csim" setup="false" optimizeCompile="false" clean="true" ldflags="" mflags=""/>
    </Simulation>
    <solutions>
        <solution name="solution1" status=""/>
    </solutions>
</AutoPilot:project>
